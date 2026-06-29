"""
因子分析模块
═══════════
ICAnalysis: Information Coefficient 分析
LayerBacktest: 分层回测（分组收益单调性检验）
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from scipy import stats
import logging

logger = logging.getLogger(__name__)


class ICAnalysis:
    """
    IC (Information Coefficient) 分析

    计算因子值与未来收益的相关性：
    - Rank IC (Spearman): 最常用，稳健
    - IC Mean / IC IR (Information Ratio = mean/std): 因子稳定性
    - IC t-stat: IC 统计显著性
    """

    def __init__(self, forward_periods: List[int] = None):
        """
        Args:
            forward_periods: 前瞻期列表，如 [5, 10, 20] 表示看未来5/10/20日收益
        """
        self.forward_periods = forward_periods or [5, 10, 20]

    def analyze(
        self,
        factor_values: Dict[str, pd.Series],
        price_data: Dict[str, pd.DataFrame],
        dates: List[str],
    ) -> pd.DataFrame:
        """
        计算因子在各时间截面的 Rank IC

        Args:
            factor_values: {date_str: Series(index=code, values=factor_score)}
            price_data: {code: DataFrame(columns=['date','close'])}

        Returns:
            DataFrame: IC 时间序列，columns 为各周期 IC
        """
        results = []
        trade_dates = sorted(factor_values.keys())

        for i, date in enumerate(trade_dates):
            factors = factor_values[date]
            if len(factors.dropna()) < 30:
                continue

            row = {'date': date}
            for horizon in self.forward_periods:
                # 找到 horizon 天后的交易日
                future_date = self._get_future_date(dates, date, horizon)
                if future_date is None:
                    continue

                forward_returns = {}
                for code in factors.index:
                    if code not in price_data:
                        continue
                    df = price_data[code]
                    cur = df[df['date'] == pd.Timestamp(date)]
                    fut = df[df['date'] == pd.Timestamp(future_date)]
                    if cur.empty or fut.empty:
                        continue
                    ret = float(fut['close'].iloc[0] / cur['close'].iloc[0] - 1)
                    forward_returns[code] = ret

                fwd = pd.Series(forward_returns)
                common = factors.index.intersection(fwd.index)
                if len(common) < 30:
                    continue

                ic, pval = stats.spearmanr(
                    factors.loc[common].values,
                    fwd.loc[common].values,
                )
                row[f'IC_{horizon}d'] = round(ic, 4)

            if any(f'IC_{h}d' in row for h in self.forward_periods):
                results.append(row)

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date')

    def summary(self, ic_df: pd.DataFrame) -> pd.DataFrame:
        """IC 汇总统计"""
        rows = []
        for col in ic_df.columns:
            ic = ic_df[col].dropna()
            if len(ic) < 5:
                continue
            ir = ic.mean() / ic.std() if ic.std() > 0 else 0
            rows.append({
                'Horizon': col,
                'IC_Mean': round(ic.mean(), 4),
                'IC_Std': round(ic.std(), 4),
                'IR': round(ir, 3),
                'IC>0_Ratio': round((ic > 0).mean(), 3),
                't_stat': round(ic.mean() / ic.std() * np.sqrt(len(ic)), 2) if ic.std() > 0 else 0,
            })
        return pd.DataFrame(rows)

    @staticmethod
    def _get_future_date(dates: List[str], current: str, offset: int) -> Optional[str]:
        """获取 offset 个交易日后日期"""
        ordered = sorted(dates)
        try:
            idx = ordered.index(current)
            target = idx + offset
            if target < len(ordered):
                return ordered[target]
        except ValueError:
            pass
        return None


class LayerBacktest:
    """
    分层回测 —— 验证因子单调性

    将股票按因子值分为 N 组，计算各组等权收益。
    如果因子有效，Top组的收益应显著高于Bottom组。
    """

    def __init__(self, n_groups: int = 10):
        self.n_groups = n_groups

    def run(
        self,
        factor_values: Dict[str, pd.Series],
        price_data: Dict[str, pd.DataFrame],
        dates: List[str],
        rebalance_freq: int = 20,  # 每20个交易日调仓
    ) -> pd.DataFrame:
        """
        运行分层回测

        Returns:
            DataFrame: 各组累计收益，columns = Group_1(最高) ... Group_N(最低)
        """
        trade_dates = sorted(factor_values.keys())
        rebalance_dates = trade_dates[::rebalance_freq]

        # 初始化各组权益
        equity = {g: [1.0] for g in range(1, self.n_groups + 1)}
        current_positions = {g: [] for g in range(1, self.n_groups + 1)}

        for i, date in enumerate(trade_dates):
            prev_date = trade_dates[i - 1] if i > 0 else date

            # 是否需要调仓
            if date in rebalance_dates:
                factors = factor_values.get(date)
                if factors is not None and len(factors.dropna()) >= self.n_groups * 3:
                    # 按因子值排序分组
                    ranked = factors.dropna().sort_values()
                    group_size = len(ranked) // self.n_groups
                    for g in range(1, self.n_groups + 1):
                        start = (g - 1) * group_size
                        end = g * group_size if g < self.n_groups else len(ranked)
                        current_positions[g] = list(ranked.index[start:end])

            # 计算各组当日收益（等权）
            for g in range(1, self.n_groups + 1):
                codes = current_positions[g]
                if not codes:
                    equity[g].append(equity[g][-1])
                    continue

                returns = []
                for code in codes:
                    if code not in price_data:
                        continue
                    df = price_data[code]
                    cur = df[df['date'] == pd.Timestamp(date)]
                    prev = df[df['date'] == pd.Timestamp(prev_date)]
                    if cur.empty or prev.empty:
                        continue
                    ret = float(cur['close'].iloc[0] / prev['close'].iloc[0] - 1)
                    returns.append(ret)

                avg_ret = np.mean(returns) if returns else 0
                equity[g].append(equity[g][-1] * (1 + avg_ret))

        # 构建 DataFrame
        df_data = {'date': [pd.Timestamp(d) for d in trade_dates]}
        for g in range(1, self.n_groups + 1):
            df_data[f'Group_{g}'] = equity[g][1:]  # 去掉初始值
        result = pd.DataFrame(df_data).set_index('date')

        # 计算多空收益
        result['LongShort'] = result[f'Group_1'] - result[f'Group_{self.n_groups}']
        return result

    def summary(self, layer_result: pd.DataFrame) -> pd.DataFrame:
        """分层收益汇总"""
        rows = []
        for col in layer_result.columns:
            cumulative = layer_result[col].iloc[-1] - 1
            daily = layer_result[col].pct_change().dropna()
            ann_ret = (1 + cumulative) ** (252 / len(daily)) - 1
            sharpe = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else 0
            max_dd = (layer_result[col].cummax() - layer_result[col]).max() / layer_result[col].cummax().max()
            rows.append({
                'Group': col,
                'CumReturn': f'{cumulative:+.2%}',
                'AnnReturn': f'{ann_ret:+.2%}',
                'Sharpe': round(sharpe, 2),
                'MaxDD': f'{max_dd:.1%}',
            })
        return pd.DataFrame(rows)
