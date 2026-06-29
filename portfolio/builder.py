"""
组合构建器
═════════
多因子加权合成 → 选股 → 风控过滤 → 输出持仓
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass, field
import logging

from data import DataFetcher
from portfolio.risk import calc_stops, kelly_position, StopLevels

logger = logging.getLogger(__name__)


def _parse_date(date: str):
    """兼容 %Y%m%d 和 %Y-%m-%d 两种格式"""
    from datetime import datetime
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {date}")


@dataclass
class Stock:
    """选股结果"""
    code: str
    name: str
    price: float
    score: float
    sector: str = ""
    market_cap: float = 0
    stop_levels: Optional[StopLevels] = None
    reason: str = ""

    @property
    def stop_loss(self) -> float:
        return self.stop_levels.stop_loss if self.stop_levels else self.price * 0.95

    @property
    def take_profit(self) -> float:
        return self.stop_levels.take_profit if self.stop_levels else self.price * 1.10

    def to_dict(self) -> dict:
        return {
            'code': self.code, 'name': self.name, 'price': self.price,
            'score': round(self.score, 1), 'sector': self.sector,
            'stop_loss': round(self.stop_loss, 2),
            'take_profit': round(self.take_profit, 2),
            'reason': self.reason,
        }

    def __repr__(self):
        return f"{self.code} {self.name} ¥{self.price:.2f} 评分:{self.score:.1f}"


@dataclass
class PortfolioConfig:
    """组合配置"""
    top_n: int = 10                        # 持仓数量
    max_weight: float = 0.10               # 单票最大仓位
    max_sector_weight: float = 0.25        # 单行业最大仓位
    min_market_cap: float = 50             # 最小市值(亿)
    require_stop: bool = True              # 是否计算动态止损
    atr_stop_mult: float = 2.0
    atr_profit_mult: float = 3.0


class PortfolioBuilder:
    """
    组合构建器

    用法：
        builder = PortfolioBuilder(config)
        stocks = builder.build(factor_scores, universe, date)
    """

    def __init__(self, config: PortfolioConfig = None):
        self.config = config or PortfolioConfig()
        self.fetcher = DataFetcher()

    def build(
        self,
        factor_scores: Dict[str, pd.Series],
        universe: pd.DataFrame,
        date: str,
        weights: Dict[str, float] = None,
    ) -> List[Stock]:
        """
        从因子得分构建持仓

        Args:
            factor_scores: {factor_name: Series(index=code)}
            universe: 股票池 DataFrame（含 code/name/sector 等）
            date: 调仓日期
            weights: 因子权重，如 {'momentum': 0.4, 'value': 0.3, 'quality': 0.3}

        Returns:
            排序后的 Stock 列表
        """
        if not factor_scores:
            return []

        # 默认等权
        if weights is None:
            weights = {name: 1.0 / len(factor_scores) for name in factor_scores}

        # 构建 code → info 映射
        info_map = {}
        for _, row in universe.iterrows():
            info_map[row['code']] = row

        # 收集所有股票的因子值
        all_codes = set()
        for s in factor_scores.values():
            all_codes.update(s.index)
        all_codes = sorted(all_codes)

        scores = np.zeros(len(all_codes))
        code_list = list(all_codes)
        valid_count = np.zeros(len(all_codes))

        for name, series in factor_scores.items():
            w = weights.get(name, 0)
            if w == 0:
                continue
            # 标准化为 Z-score
            s_norm = self._robust_normalize(series)
            for i, code in enumerate(code_list):
                if code in s_norm.index:
                    scores[i] += w * s_norm[code]
                    valid_count[i] += 1

        # 只保留至少有2个因子覆盖的股票
        mask = valid_count >= 1
        scores = scores[mask]
        valid_codes = [code_list[i] for i in range(len(code_list)) if mask[i]]

        if len(scores) == 0:
            return []

        # 基本面过滤
        filtered = []
        for i, code in enumerate(valid_codes):
            info = info_map.get(code, {})
            market_cap = float(info.get('market_cap', 0)) if isinstance(info, pd.Series) else 0
            if market_cap < self.config.min_market_cap:
                continue

            filtered.append({
                'code': code,
                'score': scores[i],
                'name': str(info.get('name', code)) if isinstance(info, pd.Series) else code,
                'price': float(info.get('price', 0)) if isinstance(info, pd.Series) else 0,
                'sector': str(info.get('sector', '')) if isinstance(info, pd.Series) else '',
                'market_cap': market_cap,
            })

        # 按评分排序取 Top N
        filtered.sort(key=lambda x: x['score'], reverse=True)
        top = filtered[:self.config.top_n]

        # 行业集中度约束
        sector_count: Dict[str, int] = {}
        picks = []
        for item in top:
            sec = item['sector']
            max_per_sector = int(self.config.top_n * self.config.max_sector_weight)
            if sector_count.get(sec, 0) >= max_per_sector and max_per_sector > 0:
                continue
            sector_count[sec] = sector_count.get(sec, 0) + 1
            picks.append(item)

        # 构建 Stock 对象 + ATR 止损
        stocks = []
        for item in picks:
            code = item['code']
            price = item['price'] if item['price'] > 0 else item.get('eps', 0) * 10 or 10.0
            stop_levels = None
            if self.config.require_stop and price > 0:
                try:
                    from datetime import datetime, timedelta
                    end_dt = _parse_date(date)
                    start_dt = end_dt - timedelta(days=60)
                    hist = self.fetcher.get_daily(code, start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"))
                    if not hist.empty:
                        stop_levels = calc_stops(
                            entry_price=item['price'], hist=hist,
                            stop_mult=self.config.atr_stop_mult,
                            profit_mult=self.config.atr_profit_mult,
                        )
                except Exception:
                    pass

            stocks.append(Stock(
                code=code, name=item['name'], price=item['price'],
                score=item['score'], sector=item['sector'],
                market_cap=item['market_cap'], stop_levels=stop_levels,
                reason=f"综合评分={item['score']:.2f}",
            ))

        return stocks

    def _robust_normalize(self, series: pd.Series) -> pd.Series:
        """稳健标准化（去极值 + Z-score）"""
        s = series.dropna()
        if len(s) < 10:
            return series
        q1, q3 = s.quantile(0.01), s.quantile(0.99)
        clipped = s.clip(q1, q3)
        std = clipped.std()
        if std == 0:
            return pd.Series(0, index=series.index)
        return (clipped - clipped.mean()) / std
