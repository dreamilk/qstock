#!/usr/bin/env python3
"""
qstock — 多因子量化选股系统
══════════════════════════════

用法:
  # 选股
  python main.py -s multifactor -n 10    # 多因子策略选10只
  python main.py -s momentum             # 动量策略
  python main.py -s value                # 价值策略

  # 回测
  python main.py -s multifactor --backtest  # 回测

  # 因子分析
  python main.py -s momentum --ic          # IC分析
  python main.py -s momentum --layer       # 分层回测

  # 列出策略
  python main.py --list
"""
import sys
import os
import argparse
import datetime
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
)
logger = logging.getLogger('qstock')

from strategy import get_strategy, STRATEGIES
from portfolio import Stock
from data import DataFetcher


def print_header():
    print("═" * 54)
    print("  qstock — 多因子量化选股系统")
    print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 54)


def run_pick(strategy_name: str, date: str, top_n: int):
    """选股模式"""
    strategy = get_strategy(strategy_name)
    print(f"\n▶ 策略: {strategy_name} (因子: {', '.join(strategy.factor_names)})")
    print(f"  日期: {date}")

    stocks = strategy(date)

    if not stocks:
        print("  结果: 无符合条件的股票")
        return

    print(f"\n  选股结果 ({len(stocks)}只):")
    print("  " + "-" * 52)

    for i, s in enumerate(stocks, 1):
        sl = f"止损{s.stop_loss:.2f}" if s.stop_loss > 0 else "—"
        tp = f"止盈{s.take_profit:.2f}" if s.take_profit > 0 else "—"
        print(f"  {i:2d}. {s.code} {s.name:<8s} ¥{s.price:>7.2f}  "
              f"评分:{s.score:>6.1f}  {sl} {tp}")

    # 保存 CSV
    import pandas as pd
    df = pd.DataFrame([s.to_dict() for s in stocks])
    filename = f"{strategy_name}_{date}.csv"
    df.to_csv(filename, encoding='utf-8-sig', index=False)
    print(f"\n  保存: {filename}")


def run_backtest(strategy_name: str):
    """回测模式"""
    from backtest import BacktestEngine

    strategy = get_strategy(strategy_name)
    engine = BacktestEngine(
        start_date='2024-01-01',
        end_date='2026-06-01',
        initial_capital=1_000_000,
    )
    print(f"\n▶ 回测: {strategy_name} (2024-01 → 2026-06)")
    print(f"  因子: {', '.join(strategy.factor_names)}")

    result = engine.run(strategy, rebalance_freq='monthly', top_n=10)
    print(result.summary())

    # 保存权益曲线
    import pandas as pd
    pd.DataFrame({'equity': result.equity_curve}).to_csv(
        f"{strategy_name}_equity.csv", index=False
    )
    print(f"  权益曲线保存: {strategy_name}_equity.csv")


def run_ic_analysis(strategy_name: str, start: str, end: str):
    """IC 分析模式"""
    from analysis import ICAnalysis
    from factors.base import BaseFactor

    strategy = get_strategy(strategy_name)
    ic = ICAnalysis(forward_periods=[5, 10, 20])

    print(f"\n▶ IC 分析: {strategy_name}")
    print(f"  因子: {', '.join(strategy.factor_names)}")
    print(f"  期间: {start} → {end}")
    print(f"  计算中...（需要逐个交易日计算因子值 + 未来收益）")

    fetcher = DataFetcher()
    dates = fetcher.get_trade_dates(start, end)
    if len(dates) < 20:
        print("  交易日不足")
        return

    # 对每个因子做 IC
    for factor in strategy._factors:
        print(f"\n  因子: {factor.name}")
        factor_vals = {}
        universe = strategy._get_universe()

        # 采样计算（每10个交易日取一个截面）
        sample_dates = dates[::10]
        for date in sample_dates:
            try:
                raw = factor.compute(date, universe)
                if not raw.empty:
                    factor_vals[date] = raw
            except Exception:
                continue

        if len(factor_vals) < 5:
            print("    数据不足")
            continue

        # 获取价格数据做 IC
        price_data = {}
        used_codes = set()
        for series in factor_vals.values():
            used_codes.update(series.index)
        used_codes = list(used_codes)[:200]  # 限制

        print(f"    加载 {len(used_codes)} 只股票价格数据...")
        for code in used_codes:
            try:
                df = fetcher.get_daily(code, start.replace('-', ''), end.replace('-', ''))
                if not df.empty:
                    price_data[code] = df[['date', 'close']]
            except Exception:
                continue

        ic_df = ic.analyze(factor_vals, price_data, sample_dates)
        if ic_df.empty:
            print("    无有效 IC 数据")
            continue

        print(ic.summary(ic_df).to_string(index=False))


def run_layer_backtest(strategy_name: str, start: str, end: str):
    """分层回测"""
    from analysis import LayerBacktest

    strategy = get_strategy(strategy_name)
    fetcher = DataFetcher()
    dates = fetcher.get_trade_dates(start, end)

    print(f"\n▶ 分层回测: {strategy_name}")
    print(f"  期间: {start} → {end}")

    # 取第一个因子做分层
    if not strategy._factors:
        print("  无可用因子")
        return

    factor = strategy._factors[0]
    print(f"  因子: {factor.name}")

    universe = strategy._get_universe()
    sample_dates = dates[::20]
    factor_vals = {}
    for date in sample_dates:
        try:
            raw = factor.compute(date, universe)
            if not raw.empty:
                factor_vals[date] = raw
        except Exception:
            continue

    if len(factor_vals) < 5:
        print("  数据不足")
        return

    # 价格数据
    price_data = {}
    used_codes = set()
    for series in factor_vals.values():
        used_codes.update(series.index)
    used_codes = list(used_codes)[:200]

    print(f"  加载 {len(used_codes)} 只股票...")
    for code in used_codes:
        try:
            df = fetcher.get_daily(code, start.replace('-', ''), end.replace('-', ''))
            if not df.empty:
                price_data[code] = df[['date', 'close']]
        except:
            continue

    lb = LayerBacktest(n_groups=5)
    result = lb.run(factor_vals, price_data, sample_dates, rebalance_freq=5)
    print("\n" + lb.summary(result).to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description='qstock — 多因子量化选股系统')
    parser.add_argument('-s', '--strategy', default='multifactor',
                        help='策略名称: momentum/value/quality/multifactor')
    parser.add_argument('-d', '--date', default=None, help='日期 YYYYMMDD')
    parser.add_argument('-n', '--top-n', type=int, default=10, help='选股数量')
    parser.add_argument('--backtest', action='store_true', help='回测模式')
    parser.add_argument('--ic', action='store_true', help='IC分析')
    parser.add_argument('--layer', action='store_true', help='分层回测')
    parser.add_argument('--list', action='store_true', help='列出策略')
    parser.add_argument('--start', default='2024-01-01', help='回测/IC起始日期')
    parser.add_argument('--end', default='2026-06-01', help='回测/IC结束日期')

    args = parser.parse_args()

    if args.list:
        print("可用策略:")
        for name, cls in STRATEGIES.items():
            s = cls()
            print(f"  {name}: 因子={s.factor_names}")
        return

    if args.date is None:
        args.date = datetime.datetime.now().strftime('%Y%m%d')

    print_header()

    if args.backtest:
        run_backtest(args.strategy)
    elif args.ic:
        run_ic_analysis(args.strategy, args.start, args.end)
    elif args.layer:
        run_layer_backtest(args.strategy, args.start, args.end)
    else:
        run_pick(args.strategy, args.date, args.top_n)


if __name__ == '__main__':
    main()
