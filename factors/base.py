"""
因子基类
═══════
所有因子继承 BaseFactor，实现 compute(date) → {symbol: factor_value}

设计：
- 因子返回 dict[symbol] = score，高分=做多方向
- 标准化为截面 Z-score（均值0，标准差1）
- 自动处理缺失值
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class BaseFactor(ABC):
    """因子基类"""

    def __init__(self, name: str, category: str = ""):
        self.name = name
        self.category = category

    @abstractmethod
    def compute(self, date: str, universe: pd.DataFrame) -> pd.Series:
        """
        计算因子值

        Args:
            date: 计算日期 YYYYMMDD
            universe: stock universe，至少含 'code' 列

        Returns:
            pd.Series(index=code, values=因子原始值, name=self.name)
        """
        ...

    def normalize(self, raw: pd.Series) -> pd.Series:
        """截面 Z-score 标准化，处理异常值"""
        if len(raw.dropna()) < 10:
            return raw
        # 去极值：保留 [Q1-3*IQR, Q3+3*IQR]
        q1, q3 = raw.quantile(0.01), raw.quantile(0.99)
        clipped = raw.clip(q1, q3)
        std = clipped.std()
        if std == 0 or np.isnan(std):
            return pd.Series(0, index=raw.index, name=self.name)
        z = (clipped - clipped.mean()) / std
        # 方向修正：高因子值 = 做多方向（因子内部保证）
        z.name = self.name
        return z

    def rank(self, raw: pd.Series) -> pd.Series:
        """截面排名 0~100"""
        ranked = raw.rank(pct=True) * 100
        ranked.name = self.name
        return ranked

    def __repr__(self):
        return f"Factor({self.name})"


def winsorize(series: pd.Series, limits: tuple = (0.01, 0.01)) -> pd.Series:
    """去极值 Winsorize"""
    lo, hi = series.quantile(limits[0]), series.quantile(1 - limits[1])
    return series.clip(lo, hi)
