"""
动量因子
═══════
- Momentum(N): 过去N日涨跌幅
- VolumeMomentum: 成交量相对变化
- RelativeStrength: 相对大盘强度
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

from factors.base import BaseFactor

logger = logging.getLogger(__name__)


def _parse_date(date: str) -> datetime:
    """兼容 %Y%m%d 和 %Y-%m-%d 两种格式"""
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {date}")


class MomentumFactor(BaseFactor):
    """
    截面动量因子 —— A股最有效的单因子之一

    计算过去N个交易日的累计收益（前复权）
    """

    def __init__(self, period: int = 60):
        super().__init__(name=f"momentum_{period}d", category="momentum")
        self.period = period

    def compute(self, date: str, universe, fetcher) -> pd.Series:
        from data import DataFetcher
        if fetcher is None:
            fetcher = DataFetcher()

        date_dt = _parse_date(date)
        start = (date_dt - timedelta(days=self.period * 2)).strftime("%Y%m%d")
        date_fmt = date_dt.strftime("%Y%m%d")

        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            try:
                hist = fetcher.get_daily(code, start, date_fmt)
                if len(hist) < self.period:
                    continue
                close = hist['close'].values
                ret = (close[-1] / close[-self.period] - 1)
                scores[code] = ret
            except Exception:
                continue

        return pd.Series(scores, name=self.name)


class MultiHorizonMomentum(BaseFactor):
    """
    多周期动量 —— 加权合成 20/60/120日动量
    """

    def __init__(self):
        super().__init__(name="momentum_multi", category="momentum")

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        from data import DataFetcher
        if fetcher is None:
            fetcher = DataFetcher()

        date_dt = _parse_date(date)
        start = (date_dt - timedelta(days=180)).strftime("%Y%m%d")
        date_fmt = date_dt.strftime("%Y%m%d")

        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            try:
                hist = fetcher.get_daily(code, start, date_fmt)
                n = len(hist)
                if n < 20:
                    continue
                close = hist['close'].values
                mom20 = (close[-1] / close[-min(20, n)] - 1)
                mom60 = (close[-1] / close[-min(60, n)] - 1) if n >= 60 else mom20
                mom120 = (close[-1] / close[-min(120, n)] - 1) if n >= 120 else mom60
                # 权重配置：近端动量更关键
                score = mom20 * 0.40 + mom60 * 0.35 + mom120 * 0.25
                scores[code] = score
            except Exception:
                continue

        return pd.Series(scores, name=self.name)


class VolumeMomentum(BaseFactor):
    """成交量动量 —— 量比变化"""

    def __init__(self, short: int = 5, long: int = 20):
        super().__init__(name=f"vol_mom_{short}_{long}", category="momentum")
        self.short = short
        self.long = long

    def compute(self, date: str, universe, fetcher=None) -> pd.Series:
        from data import DataFetcher
        if fetcher is None:
            fetcher = DataFetcher()

        date_dt = _parse_date(date)
        start = (date_dt - timedelta(days=60)).strftime("%Y%m%d")
        date_fmt = date_dt.strftime("%Y%m%d")

        scores = {}
        for _, row in universe.iterrows():
            code = row['code']
            try:
                hist = fetcher.get_daily(code, start, date_fmt)
                if len(hist) < self.long:
                    continue
                vol = hist['volume'].values
                vol_short = vol[-self.short:].mean()
                vol_long = vol[-self.long:].mean()
                if vol_long > 0:
                    scores[code] = vol_short / vol_long
            except Exception:
                continue

        return pd.Series(scores, name=self.name)
