"""
质量因子
═══════
- ROE: 净资产收益率
- GrossMargin: 毛利率
- DebtRatio: 资产负债率（取反，低负债高分）
- Piotroski: F-Score (0-9)
"""
import pandas as pd
import numpy as np
from typing import Dict
import logging

from factors.base import BaseFactor

logger = logging.getLogger(__name__)


class ROEFactor(BaseFactor):
    """ROE因子"""

    def __init__(self):
        super().__init__(name="roe", category="quality")

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            roe = row.get('roe', 0)
            if isinstance(roe, (int, float)) and not np.isnan(roe):
                scores[code] = roe
        return pd.Series(scores, name=self.name)


class GrossMarginFactor(BaseFactor):
    """毛利率因子"""

    def __init__(self):
        super().__init__(name="gross_margin", category="quality")

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            gm = row.get('gross_margin', 0)
            if isinstance(gm, (int, float)) and gm > 0:
                scores[code] = gm
        return pd.Series(scores, name=self.name)


class DebtRatioFactor(BaseFactor):
    """负债率因子 —— 取反，低负债=高分"""

    def __init__(self):
        super().__init__(name="debt_ratio", category="quality")

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            debt = row.get('debt_ratio', 100)
            if isinstance(debt, (int, float)) and debt > 0:
                scores[code] = -debt  # 取反
        return pd.Series(scores, name=self.name)


class PiotroskiFactor(BaseFactor):
    """
    Piotroski F-Score 因子 (0-9)
    基于 akshare 个股基本面数据，9项二元评分
    """

    def __init__(self):
        super().__init__(name="piotroski_f", category="quality")

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        from data import DataFetcher
        if fetcher is None:
            fetcher = DataFetcher()

        # 获取基本面
        codes = universe['code'].tolist()
        fund = fetcher.get_fundamentals(codes)
        if fund.empty:
            return pd.Series(name=self.name)

        fund = fund.set_index('code')
        scores = {}
        for code in fund.index:
            if code not in fund.index:
                continue
            row = fund.loc[code]
            f = 0
            # 盈利
            if row.get('roe', 0) > 0:
                f += 1
            if row.get('net_profit', 0) > 0:
                f += 1
            # 财务健康
            if row.get('debt_ratio', 100) < 60:
                f += 1
            if row.get('current_ratio', 0) > 1:
                f += 1
            # 质量
            gm = row.get('gross_margin', 0)
            if isinstance(gm, (int, float)):
                if gm > 15:
                    f += 1
                if gm > 30:
                    f += 1
            if row.get('roe', 0) > 8:
                f += 1
            # 股息
            if row.get('dividend_yield', 0) > 1:
                f += 1
            # 市值
            if row.get('market_cap', 0) > 100:
                f += 1

            scores[code] = f

        return pd.Series(scores, name=self.name)
