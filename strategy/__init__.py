"""
策略注册表
═════════
多因子量化策略集合
"""
from strategy.base import Strategy
from factors.impl.momentum import MultiHorizonMomentum, VolumeMomentum
from factors.impl.value import PEFactor, PBFactor, DividendFactor
from factors.impl.quality import ROEFactor, GrossMarginFactor, DebtRatioFactor, PiotroskiFactor


class MomentumStrategy(Strategy):
    """纯动量策略 —— 强者恒强"""
    def _init_factors(self):
        return [MultiHorizonMomentum()]

    def _get_weights(self):
        return {"momentum_multi": 1.0}


class ValueStrategy(Strategy):
    """价值策略 —— 低PE + 低PB + 高股息"""
    def _init_factors(self):
        return [PEFactor(), PBFactor(), DividendFactor()]

    def _get_weights(self):
        return {"ep_ttm": 0.40, "bp": 0.35, "dividend_yield": 0.25}


class QualityStrategy(Strategy):
    """质量策略 —— 高ROE + 高毛利率 + 低负债 + Piotroski"""
    def _init_factors(self):
        return [ROEFactor(), GrossMarginFactor(), DebtRatioFactor(), PiotroskiFactor()]

    def _get_weights(self):
        return {"roe": 0.30, "gross_margin": 0.25, "debt_ratio": 0.20, "piotroski_f": 0.25}


class MultiFactorStrategy(Strategy):
    """
    多因子合成策略 —— 动量 + 价值 + 质量

    权重：动量40% + 价值35% + 质量25%
    """
    def _init_factors(self):
        return [
            MultiHorizonMomentum(),
            PEFactor(),
            PBFactor(),
            ROEFactor(),
            DebtRatioFactor(),
            PiotroskiFactor(),
        ]

    def _get_weights(self):
        return {
            "momentum_multi": 0.40,
            "ep_ttm": 0.20,
            "bp": 0.15,
            "roe": 0.10,
            "debt_ratio": 0.05,
            "piotroski_f": 0.10,
        }


# 策略注册表
STRATEGIES = {
    'momentum': MomentumStrategy,
    'value': ValueStrategy,
    'quality': QualityStrategy,
    'multifactor': MultiFactorStrategy,
}


def get_strategy(name: str) -> Strategy:
    name_lower = name.lower()
    if name_lower not in STRATEGIES:
        raise ValueError(f"未知策略 '{name}'，可用: {list(STRATEGIES.keys())}")
    return STRATEGIES[name_lower]()
