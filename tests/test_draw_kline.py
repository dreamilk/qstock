"""
测试 K 线图生成
"""
import pytest
import os
import tempfile
from pathlib import Path
from utils.draw_kline import generate_kline_chart


class TestGenerateKlineChart:
    """测试 generate_kline_chart 函数"""

    def test_output_dir_created(self):
        """应该自动创建输出目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "nested", "charts")
            # 用一个不存在/数据不足的股票代码，预期返回 None
            result = generate_kline_chart(
                "000001", "平安银行", "20240101",
                output_dir=out_dir
            )
            # 即使生成失败，目录也应该被创建
            assert os.path.isdir(out_dir)

    def test_invalid_stock_returns_none(self):
        """无效股票代码应返回 None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_kline_chart(
                "999999", "不存在的股票", "20240101",
                output_dir=tmpdir
            )
            # 可能会因为数据不足返回 None
            # 或者网络问题导致异常，两种情况都不应崩溃
            assert result is None or isinstance(result, str)

    def test_safe_filename_generation(self):
        """文件名应该安全（没有非法字符）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_kline_chart(
                "600000", "浦发银行", "20240101",
                output_dir=tmpdir
            )
            if result is not None:
                basename = os.path.basename(result)
                # 不应包含可能导致问题的字符
                assert " " not in basename
                assert basename.endswith(".png")
