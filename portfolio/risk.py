"""
风险管理模块
═══════════
- ATR 动态止损/止盈
- Kelly 仓位管理
- 波动率目标仓位
- 追迹止损
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class StopLevels:
    """止损止盈配置"""
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float
    risk_pct: float
    reward_pct: float

    def __repr__(self):
        return (f"入场={self.entry_price:.2f} "
                f"止损={self.stop_loss:.2f}(-{self.risk_pct:.1%}) "
                f"止盈={self.take_profit:.2f}(+{self.reward_pct:.1%}) "
                f"ATR={self.atr:.2f}")


def calc_atr(hist: pd.DataFrame, period: int = 14) -> float:
    """计算ATR"""
    if len(hist) < period:
        return float(hist['high'].tail(period).mean() - hist['low'].tail(period).mean())

    high = hist['high'].astype(float)
    low = hist['low'].astype(float)
    close = hist['close'].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return float(tr.tail(period).mean())


def calc_stops(
    entry_price: float,
    hist: pd.DataFrame,
    atr_period: int = 14,
    stop_mult: float = 2.0,
    profit_mult: float = 3.0,
) -> StopLevels:
    """基于ATR计算止损止盈"""
    atr = calc_atr(hist, atr_period)
    if atr <= 0:
        atr = entry_price * 0.03  # 回退到3%

    stop_loss = round(entry_price - stop_mult * atr, 2)
    take_profit = round(entry_price + profit_mult * atr, 2)
    risk_pct = (entry_price - stop_loss) / entry_price
    reward_pct = (take_profit - entry_price) / entry_price

    return StopLevels(
        entry_price=entry_price, stop_loss=max(stop_loss, 0.01),
        take_profit=max(take_profit, entry_price * 1.01),
        atr=atr, risk_pct=risk_pct, reward_pct=reward_pct,
    )


def calc_trailing_stop(
    entry_price: float,
    highest_price: float,
    current_atr: float,
    trail_mult: float = 3.0,
) -> float:
    """追迹止损 —— 随价格上涨自动上移"""
    floor = entry_price - trail_mult * current_atr
    from_high = highest_price - trail_mult * current_atr
    return max(floor, from_high)


def kelly_position(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    fraction: float = 0.5,
) -> float:
    """
    凯利公式仓位

    f* = p - (1-p) / (W/L)
    fraction=0.5 表示半凯利（保守）
    """
    if avg_loss_pct <= 0.001:
        return 0.1
    b = avg_win_pct / avg_loss_pct
    kelly = win_rate - (1 - win_rate) / b
    return max(0.02, min(kelly * fraction, 0.25))


def volatility_target(
    returns: pd.Series,
    target_ann_vol: float = 0.15,
) -> float:
    """
    波动率目标仓位

    仓位 = target_vol / realized_vol
    """
    if len(returns) < 20:
        return 1.0
    realized = returns.tail(20).std() * np.sqrt(252)
    if realized <= 0:
        return 1.0
    position = target_ann_vol / realized
    return np.clip(position, 0.10, 1.0)
