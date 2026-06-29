"""
策略基类
═══════
Strategy 封装：因子组合 + 组合构建 = 输出持仓

子类只需定义 factors 和 weights。
"""
from abc import ABC, abstractmethod
from typing import List, Dict
import pandas as pd
import logging

from data import DataFetcher
from factors.base import BaseFactor
from portfolio import PortfolioBuilder, PortfolioConfig, Stock
from portfolio.risk import calc_stops

logger = logging.getLogger(__name__)


class Strategy(ABC):
    """
    策略基类

    子类实现：
        _init_factors() → List[BaseFactor]  # 定义使用的因子
        _get_weights() → Dict[str, float]   # 定义因子权重

    调用：
        strategy(date) → List[Stock]         # 选股
    """

    def __init__(self, name: str = ""):
        self.name = name or self.__class__.__name__
        self.fetcher = DataFetcher()
        self._factors: List[BaseFactor] = self._init_factors()
        self._weights: Dict[str, float] = self._get_weights()
        self._builder = PortfolioBuilder()

    @abstractmethod
    def _init_factors(self) -> List[BaseFactor]:
        """初始化因子列表"""
        ...

    @abstractmethod
    def _get_weights(self) -> Dict[str, float]:
        """因子权重配置"""
        ...

    def __call__(self, date: str) -> List[Stock]:
        """
        执行选股

        Args:
            date: YYYYMMDD 格式

        Returns:
            排序后的 Stock 列表
        """
        # 1. 获取股票池
        universe = self._get_universe()

        # 2. 计算各因子值
        factor_scores = {}
        for factor in self._factors:
            try:
                # 尝试传 fetcher（动量等因子需要），失败则回退
                import inspect
                sig = inspect.signature(factor.compute)
                if 'fetcher' in sig.parameters:
                    raw = factor.compute(date, universe, fetcher=self.fetcher)
                else:
                    raw = factor.compute(date, universe)
                if not raw.empty:
                    factor_scores[factor.name] = raw
            except Exception as e:
                logger.warning(f"因子 {factor.name} 计算异常: {e}")

        # 3. 组合构建
        stocks = self._builder.build(
            factor_scores=factor_scores,
            universe=universe,
            date=date,
            weights=self._weights,
        )

        return stocks

    def _get_universe(self) -> 'pd.DataFrame':
        """获取股票池（主板，非ST，市值>50亿）"""
        spot = self.fetcher.get_spot()
        if spot.empty:
            return spot

        mask = (
            spot['code'].str.startswith(('00', '60')) &
            ~spot['name'].str.contains('ST', na=False)
        )
        return spot[mask].copy()

    @property
    def factor_names(self) -> List[str]:
        return [f.name for f in self._factors]
