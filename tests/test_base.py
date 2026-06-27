"""
测试 Stock 数据类和策略基类
"""
import pytest
import pandas as pd
from dataclasses import is_dataclass, fields

from strategy.base import Stock, Strategy, toDataFrame


class TestStock:
    """测试 Stock 数据类"""

    def test_is_dataclass(self):
        """Stock 应该是 dataclass"""
        assert is_dataclass(Stock)

    def test_default_values(self):
        """默认值应该正确"""
        s = Stock()
        assert s.code == ""
        assert s.name == ""
        assert s.current_price == 0.0
        assert s.buy_price == 0.0
        assert s.sell_price == 0.0
        assert s.stop_loss == 0.0
        assert s.suggest_reason == ""
        assert s.score == 0.0

    def test_instances_are_independent(self):
        """多个实例之间不应互相影响（之前是类属性共享 Bug）"""
        s1 = Stock()
        s2 = Stock()
        s1.code = "000001"
        s2.code = "000002"
        assert s1.code == "000001"
        assert s2.code == "000002"
        assert s1.code != s2.code

    def test_full_initialization(self):
        """测试完整的属性设置"""
        s = Stock()
        s.code = "000001"
        s.name = "平安银行"
        s.current_price = 12.50
        s.buy_price = 12.45
        s.sell_price = 13.50
        s.stop_loss = 11.80
        s.suggest_reason = "测试理由"
        s.score = 85.5
        
        assert s.code == "000001"
        assert s.name == "平安银行"
        assert s.current_price == 12.50
        assert s.buy_price == 12.45
        assert s.sell_price == 13.50
        assert s.stop_loss == 11.80
        assert s.score == 85.5

    def test_to_dict(self):
        """to_dict 应该返回包含所有字段的字典"""
        s = Stock()
        s.code = "000001"
        s.name = "测试"
        s.score = 90.0
        d = s.to_dict()
        assert d["code"] == "000001"
        assert d["name"] == "测试"
        assert d["score"] == 90.0
        assert "stop_loss" in d  # 新增字段

    def test_str_representation(self):
        """__str__ 应该包含关键信息"""
        s = Stock()
        s.code = "000001"
        s.name = "测试"
        s.current_price = 10.0
        s.buy_price = 10.0
        s.sell_price = 11.0
        s.suggest_reason = "reason"
        result = str(s)
        assert "000001" in result
        assert "测试" in result


class TestToDataFrame:
    """测试 toDataFrame 函数"""

    def test_empty_list(self):
        """空列表应返回空 DataFrame"""
        df = toDataFrame([])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_single_stock(self):
        """单个 Stock 应正确转换"""
        s = Stock()
        s.code = "000001"
        s.name = "测试"
        s.score = 85.0
        df = toDataFrame([s])
        assert len(df) == 1
        assert df.iloc[0]["code"] == "000001"
        assert df.iloc[0]["name"] == "测试"
        assert df.iloc[0]["score"] == 85.0

    def test_multiple_stocks(self):
        """多个 Stock 应正确转换并保留顺序"""
        stocks = []
        for i in range(3):
            s = Stock()
            s.code = f"00000{i+1}"
            s.score = (3 - i) * 10
            stocks.append(s)
        df = toDataFrame(stocks)
        assert len(df) == 3
        assert list(df["code"]) == ["000001", "000002", "000003"]


class TestStrategy:
    """测试 Strategy 基类"""

    def test_strategy_name(self):
        """策略名应正确设置"""
        s = Strategy("test")
        assert s.name == "test"

    def test_filter_stocks_not_implemented(self):
        """未实现 filter_stocks 应抛出 NotImplementedError"""
        s = Strategy("test")
        with pytest.raises(NotImplementedError):
            s.filter_stocks("20240101")
