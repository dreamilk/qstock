"""
回测引擎
═══════
逐日盯市回测，计算真实盈亏。

架构：
- 每日迭代所有交易日
- 调仓日：卖出不在新列表的持仓，买入新的，扣交易成本
- 非调仓日：按实时价格计算持仓市值
- 输出：权益曲线、日收益、交易记录
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import logging

from data import DataFetcher
from portfolio import Stock

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """交易记录"""
    date: str
    code: str
    action: str  # 'buy' or 'sell'
    price: float
    shares: int
    cost: float  # 含佣金

@dataclass
class Position:
    """持仓"""
    code: str
    shares: int
    avg_cost: float  # 平均成本
    entry_date: str


class BacktestEngine:
    """
    逐日盯市回测引擎

    用法:
        engine = BacktestEngine('2023-01-01', '2025-12-31')
        result = engine.run(strategy)  # strategy 返回 List[Stock]
        result.summary()
    """

    def __init__(
        self,
        start_date: str,
        end_date: str,
        initial_capital: float = 1_000_000,
        commission: float = 0.00025,    # 万2.5佣金
        stamp_duty: float = 0.001,       # 千1印花税（仅卖出）
        benchmark_code: str = "000001",  # 上证指数
        min_shares: int = 100,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.commission = commission
        self.stamp_duty = stamp_duty
        self.benchmark_code = benchmark_code
        self.min_shares = min_shares

        self.fetcher = DataFetcher()
        self.positions: Dict[str, Position] = {}
        self.cash = initial_capital
        self.trades: List[Trade] = []
        self.equity: List[float] = []
        self.daily_returns: List[float] = []

        # 日内累计手续费（用于熔断检查）
        self._daily_commission = 0.0

    # ═══ 运行 ═══

    def run(
        self,
        strategy,
        rebalance_freq: str = "monthly",
        top_n: int = 10,
        max_weight: float = 0.10,
    ) -> 'BacktestResult':
        """
        运行回测

        Args:
            strategy: 返回 List[Stock] 的选股函数/对象
            rebalance_freq: 'weekly' 或 'monthly'
            top_n: 持仓数量
            max_weight: 单票最大仓位
        """
        trade_dates = self.fetcher.get_trade_dates(self.start_date, self.end_date)
        if len(trade_dates) < 30:
            raise ValueError(f"交易日不足: {len(trade_dates)}")

        rebalance_dates = self._rebalance_schedule(trade_dates, rebalance_freq)

        # 预加载价格数据（缓存加速）
        price_cache: Dict[str, pd.DataFrame] = {}
        used_codes = set()

        equity_curve = [self.initial_capital]
        daily_returns = []
        self.cash = self.initial_capital
        self.positions = {}
        self.trades = []

        for i, date in enumerate(trade_dates):
            # 调仓
            if date in rebalance_dates or i == 0:
                try:
                    picks = strategy(date)
                    if picks:
                        self._rebalance(picks, date, trade_dates, max_weight)
                        for s in picks:
                            used_codes.add(s.code)
                except Exception as e:
                    logger.warning(f"调仓失败 {date}: {e}")

            # 当日盯市
            total_value = self._mark_to_market(date, trade_dates, used_codes)
            equity_curve.append(total_value)

            if i > 0 and equity_curve[-2] > 0:
                ret = equity_curve[-1] / equity_curve[-2] - 1
                daily_returns.append(ret)

        # 计算指标
        result = BacktestResult(
            equity_curve=equity_curve,
            daily_returns=daily_returns,
            trades=self.trades,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            benchmark_return=self._benchmark_return(trade_dates),
        )

        self.equity = equity_curve
        self.daily_returns = daily_returns
        return result

    # ═══ 内部方法 ═══

    def _rebalance(self, picks: List[Stock], date: str, all_dates: List[str], max_weight: float):
        """调仓：卖出旧持仓，买入新标的"""
        new_codes = {s.code for s in picks}
        code_price_map = {s.code: s.price for s in picks}

        # 1. 卖出不在新列表的持仓
        for code in list(self.positions.keys()):
            if code not in new_codes:
                sell_price = self._get_price(code, date, all_dates)
                if sell_price is None:
                    sell_price = self.positions[code].avg_cost
                self._execute_sell(code, sell_price, date)

        # 2. 买入新标的（等权）
        n = len(picks)
        if n == 0:
            return

        per_weight = min(max_weight, 1.0 / n)
        total_equity = self.cash + self._positions_value(date, all_dates)
        per_cash = total_equity * per_weight

        for stock in picks:
            if stock.code in self.positions:
                continue  # 已持有

            buy_price = stock.price
            if buy_price <= 0:
                continue

            shares = int(per_cash / buy_price / self.min_shares) * self.min_shares
            if shares < self.min_shares:
                continue

            cost = shares * buy_price * (1 + self.commission)
            if cost > self.cash:
                continue

            self.cash -= cost
            self.positions[stock.code] = Position(
                code=stock.code, shares=shares,
                avg_cost=buy_price, entry_date=date,
            )
            self.trades.append(Trade(
                date=date, code=stock.code, action='buy',
                price=buy_price, shares=shares, cost=cost,
            ))

    def _execute_sell(self, code: str, price: float, date: str):
        """执行卖出"""
        pos = self.positions[code]
        proceeds = pos.shares * price * (1 - self.commission - self.stamp_duty)
        self.cash += proceeds
        self.trades.append(Trade(
            date=date, code=code, action='sell',
            price=price, shares=pos.shares, cost=proceeds,
        ))
        del self.positions[code]

    def _mark_to_market(self, date: str, all_dates: List[str], used_codes: set) -> float:
        """按当日价格计算持仓市值"""
        if not self.positions:
            return self.cash

        positions_value = 0
        for code, pos in self.positions.items():
            price = self._get_price(code, date, all_dates)
            if price is None:
                price = pos.avg_cost
            positions_value += pos.shares * price

        return self.cash + positions_value

    def _positions_value(self, date: str, all_dates: List[str]) -> float:
        """当前持仓市值"""
        val = 0
        for code, pos in self.positions.items():
            price = self._get_price(code, date, all_dates)
            if price is not None:
                val += pos.shares * price
            else:
                val += pos.shares * pos.avg_cost
        return val

    def _get_price(self, code: str, date: str, all_dates: List[str]) -> Optional[float]:
        # 查找前5个交易日范围内的数据
        date_idx = all_dates.index(date) if date in all_dates else -1
        if date_idx < 0:
            return None
        lookback = max(0, date_idx - 5)
        start_str = all_dates[lookback]
        end_str = date

        # 转换为 YYYYMMDD 格式
        start_ymd = pd.Timestamp(start_str).strftime("%Y%m%d")
        end_ymd = pd.Timestamp(end_str).strftime("%Y%m%d")

        try:
            df = self.fetcher.get_daily(code, start_ymd, end_ymd)
            if df.empty:
                return None
            return float(df['close'].iloc[-1])
        except Exception:
            return None

    def _rebalance_schedule(self, dates: List[str], freq: str) -> List[str]:
        """生成调仓日列表"""
        result = [dates[0]]
        for i in range(1, len(dates)):
            d = pd.Timestamp(dates[i])
            d_prev = pd.Timestamp(dates[i - 1])
            if freq == "weekly":
                if d.weekday() == 0 or d.month != d_prev.month:
                    result.append(dates[i])
            elif freq == "monthly":
                if d.month != d_prev.month:
                    result.append(dates[i])
            else:
                result.append(dates[i])
        return result

    def _benchmark_return(self, trade_dates: List[str]) -> float:
        """基准（上证指数）收益"""
        try:
            start_dt = pd.Timestamp(trade_dates[0])
            end_dt = pd.Timestamp(trade_dates[-1])
            idx = self.fetcher.get_index_daily(
                self.benchmark_code,
                start_dt.strftime("%Y%m%d"),
                end_dt.strftime("%Y%m%d"),
            )
            if len(idx) >= 2:
                return float(idx['close'].iloc[-1] / idx['close'].iloc[0] - 1)
        except Exception:
            pass
        return 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    equity_curve: List[float]
    daily_returns: List[float]
    trades: List[Trade]
    start_date: str
    end_date: str
    initial_capital: float
    benchmark_return: float = 0.0

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else self.initial_capital

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_capital - 1

    @property
    def annual_return(self) -> float:
        days = len(self.daily_returns)
        if days == 0:
            return 0
        years = days / 252
        return (1 + self.total_return) ** (1 / max(years, 0.1)) - 1

    @property
    def sharpe_ratio(self) -> float:
        rets = pd.Series(self.daily_returns)
        if rets.std() == 0:
            return 0
        return float(rets.mean() / rets.std() * np.sqrt(252))

    @property
    def max_drawdown(self) -> float:
        curve = pd.Series(self.equity_curve)
        peak = curve.cummax()
        dd = (curve - peak) / peak
        return float(dd.min())

    @property
    def win_rate(self) -> float:
        buy_trades = [t for t in self.trades if t.action == 'buy']
        sell_trades = [t for t in self.trades if t.action == 'sell']
        if not sell_trades:
            return 0
        # 简化：统计卖出 vs 买入成本
        wins = 0
        for st in sell_trades:
            matching_buys = [t for t in buy_trades if t.code == st.code]
            if matching_buys and st.price * st.shares > matching_buys[-1].price * st.shares:
                wins += 1
        return wins / len(sell_trades) if sell_trades else 0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def alpha(self) -> float:
        return self.annual_return - self.benchmark_return

    def summary(self) -> str:
        lines = [
            "═" * 54,
            f"  回测: {self.start_date} → {self.end_date}",
            "═" * 54,
            f"  初始资金: ¥{self.initial_capital:,.0f}",
            f"  最终权益: ¥{self.final_equity:,.0f}",
            f"  总收益率: {self.total_return:+.2%}",
            f"  年化收益: {self.annual_return:+.2%}",
            f"  夏普比率: {self.sharpe_ratio:.2f}",
            f"  最大回撤: {self.max_drawdown:.2%}",
            f"  胜率:     {self.win_rate:.1%}",
            f"  交易次数: {self.total_trades}",
            f"  基准收益: {self.benchmark_return:+.2%}",
            f"  Alpha:    {self.alpha:+.2%}",
            "═" * 54,
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            'total_return': self.total_return,
            'annual_return': self.annual_return,
            'sharpe': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate,
            'trades': self.total_trades,
            'alpha': self.alpha,
        }
