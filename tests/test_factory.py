"""
测试策略工厂
"""
import pytest
from strategy.factory import get_strategy
from strategy.dragonhead import DragonHeadStrategy
from strategy.hit_board import HitBoardStrategy
from strategy.custom import CustomStrategy
from strategy.low_stock import LowStockStrategy


class TestStrategyFactory:
    """测试策略工厂函数"""

    def test_get_dragonhead(self):
        s = get_strategy("dragonhead")
        assert isinstance(s, DragonHeadStrategy)
        assert s.name == "dragonhead"

    def test_get_dragonhead_case_insensitive(self):
        s = get_strategy("DragonHead")
        assert isinstance(s, DragonHeadStrategy)

    def test_get_hit_board(self):
        s = get_strategy("hit_board")
        assert isinstance(s, HitBoardStrategy)
        assert s.name == "hit_board"

    def test_get_custom(self):
        s = get_strategy("custom")
        assert isinstance(s, CustomStrategy)
        assert s.name == "custom"

    def test_get_low_stock(self):
        s = get_strategy("low_stock")
        assert isinstance(s, LowStockStrategy)
        assert s.name == "low_stock"

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("nonexistent")
