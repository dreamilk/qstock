"""
价值因子
═══════
- PE: 市盈率（倒数，高=低估）
- PB: 市净率（倒数）
- PS: 市销率（倒数）
- DividendYield: 股息率
- EP1Y: 1年盈利收益率变化
"""
import pandas as pd
import numpy as np
from typing import Dict
import logging

from factors.base import BaseFactor

logger = logging.getLogger(__name__)


class PEFactor(BaseFactor):
    """PE因子 —— 取倒数，高值=低PE=低估"""

    def __init__(self):
        super().__init__(name="ep_ttm", category="value")

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        from data import DataFetcher
        if fetcher is None:
            fetcher = DataFetcher()

        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            pe = row.get('pe_ttm', 0)
            if isinstance(pe, (int, float)) and pe > 0 and pe < 200:
                scores[code] = 1.0 / pe
                continue
            # 回退：从 fetcher 获取
            try:
                fund = fetcher.get_fundamentals([code])
                if not fund.empty:
                    pe = fund.iloc[0].get('pe_ttm', 0)
                    if isinstance(pe, (int, float)) and pe > 0 and pe < 200:
                        scores[code] = 1.0 / pe
            except Exception:
                pass
        return pd.Series(scores, name=self.name)


class PBFactor(BaseFactor):
    """PB因子 —— 取倒数"""

    def __init__(self):
        super().__init__(name="bp", category="value")

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        from data import DataFetcher
        if fetcher is None:
            fetcher = DataFetcher()
        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            pb = row.get('pb', 0)
            if isinstance(pb, (int, float)) and pb > 0 and pb < 50:
                scores[code] = 1.0 / pb
                continue
            try:
                fund = fetcher.get_fundamentals([code])
                if not fund.empty:
                    pb = fund.iloc[0].get('pb', 0)
                    if isinstance(pb, (int, float)) and pb > 0 and pb < 50:
                        scores[code] = 1.0 / pb
            except: pass
        return pd.Series(scores, name=self.name)


class DividendFactor(BaseFactor):
    """股息率因子"""

    def __init__(self):
        super().__init__(name="dividend_yield", category="value")

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            div = row.get('dividend_yield', 0)
            if isinstance(div, (int, float)) and div > 0:
                scores[code] = div
        return pd.Series(scores, name=self.name)
