"""
测试 broker 回测模块
"""
import pytest
import numpy as np

# pybroker 是可选依赖，未安装时跳过
pybroker = pytest.importorskip("pybroker", reason="pybroker 未安装")
from broker import calculate_kdj, make_kdj_strategy


class TestCalculateKDJ:
    """测试 KDJ 指标计算"""

    def test_output_shapes(self):
        """返回的 K、D、J 数组长度应与输入一致"""
        close = np.array([10.0] * 20)
        high = np.array([10.5] * 20)
        low = np.array([9.5] * 20)
        k, d, j = calculate_kdj(close, high, low, n=9)
        assert len(k) == 20
        assert len(d) == 20
        assert len(j) == 20

    def test_initial_values(self):
        """第一个 K 和 D 值应为 50"""
        close = np.array([10.0, 10.5, 10.3, 10.8, 10.6] * 4)
        high = np.array([11.0] * 20)
        low = np.array([9.0] * 20)
        k, d, j = calculate_kdj(close, high, low, n=9)
        assert k[0] == 50.0
        assert d[0] == 50.0

    def test_j_relation(self):
        """J = 3K - 2D"""
        close = np.random.uniform(10, 15, 30)
        high = close + np.random.uniform(0.5, 1.5, 30)
        low = close - np.random.uniform(0.5, 1.5, 30)
        k, d, j = calculate_kdj(close, high, low)
        for i in range(len(j)):
            assert abs(j[i] - (3 * k[i] - 2 * d[i])) < 1e-10

    def test_all_same_price(self):
        """所有价格相同时，KDJ 应有合理行为"""
        close = np.array([10.0] * 15)
        high = np.array([10.0] * 15)
        low = np.array([10.0] * 15)
        k, d, j = calculate_kdj(close, high, low)
        # RSV = 50 当 high == low
        # 后续 K/D 向 50 收敛
        assert len(k) == 15


class TestMakeKdjStrategy:
    """测试策略函数创建"""

    def test_returns_callable(self):
        """应返回可调用对象"""
        strat_fn = make_kdj_strategy()
        assert callable(strat_fn)

    def test_custom_percent(self):
        """应接受自定义仓位比例"""
        strat_fn = make_kdj_strategy(percent=0.3)
        assert callable(strat_fn)
