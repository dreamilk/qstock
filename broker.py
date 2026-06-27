"""
KDJ 策略回测模块

使用 pybroker 对 A 股进行 KDJ 指标策略回测（pybroker 为可选依赖）。

用法:
    pip install pybroker
    python broker.py
"""
import matplotlib
matplotlib.use('Agg')  # headless 模式，不弹窗口
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict


def calculate_kdj(close, high, low, n=9):
    """计算 KDJ 指标"""
    # 获取周期内的最高价和最低价
    highest_high = np.array([max(high[max(0, i-n+1):i+1]) for i in range(len(high))])
    lowest_low = np.array([min(low[max(0, i-n+1):i+1]) for i in range(len(low))])
    
    # 计算 RSV
    rsv = np.zeros_like(close)
    for i in range(len(close)):
        if highest_high[i] == lowest_low[i]:
            rsv[i] = 50
        else:
            rsv[i] = 100 * (close[i] - lowest_low[i]) / (highest_high[i] - lowest_low[i])
    
    # 初始化 K、D 值
    k = np.zeros_like(close)
    d = np.zeros_like(close)
    k[0] = 50
    d[0] = 50
    
    for i in range(1, len(close)):
        k[i] = 2/3 * k[i-1] + 1/3 * rsv[i]
        d[i] = 2/3 * d[i-1] + 1/3 * k[i]
    
    j = 3 * k - 2 * d
    return k, d, j


def make_kdj_strategy(percent: float = 0.25):
    """创建 KDJ 交易策略函数"""
    from pybroker import ExecContext  # lazy import — pybroker is optional
    entry_prices: Dict[str, float] = {}

    def kdj_strategy(ctx: ExecContext):
        nonlocal entry_prices
        symbol = ctx.symbol
        pos = ctx.long_pos()
        
        # 卖出逻辑
        if pos:
            if symbol in entry_prices:
                entry_price = entry_prices[symbol]
                current_price = ctx.close[-1]
                current_return = (current_price - entry_price) / entry_price * 100
                
                # 止损：亏损超过 5%
                if current_return < -5:
                    ctx.sell_shares = pos.shares
                    print(f"止损卖出 {symbol}，持有天数: {pos.bars}，收益率: {current_return:.2f}%")
                    if ctx.sell_shares == pos.shares:
                        entry_prices.pop(symbol, None)
                    return
                
                # 止盈：收益超过 10%
                if current_return > 10:
                    ctx.sell_shares = pos.shares
                    print(f"止盈卖出 {symbol}，持有天数: {pos.bars}，收益率: {current_return:.2f}%")
                    if ctx.sell_shares == pos.shares:
                        entry_prices.pop(symbol, None)
                    return
                
                # 最大持有 5 天
                if pos.bars >= 5:
                    ctx.sell_shares = pos.shares
                    print(f"持有时间到期卖出 {symbol}，持有天数: {pos.bars}，收益率: {current_return:.2f}%")
                    if ctx.sell_shares == pos.shares:
                        entry_prices.pop(symbol, None)
                    return
                
                # 连续 2 天下跌且跌幅超 3%
                if len(ctx.close) >= 3:
                    pct1 = (ctx.close[-1] - ctx.close[-2]) / ctx.close[-2] * 100
                    pct2 = (ctx.close[-2] - ctx.close[-3]) / ctx.close[-3] * 100
                    if pct1 < 0 and pct2 < 0 and (pct1 + pct2) < -3:
                        ctx.sell_shares = pos.shares
                        print(f"连续下跌卖出 {symbol}，持有天数: {pos.bars}，收益率: {current_return:.2f}%")
                        if ctx.sell_shares == pos.shares:
                            entry_prices.pop(symbol, None)
                        return
        
        # 买入逻辑：KDJ 金叉
        try:
            close_values = ctx.close
            high_values = ctx.high
            low_values = ctx.low
            
            if len(close_values) < 14:
                return
            
            k, d, j = calculate_kdj(close_values, high_values, low_values, n=9)
            
            if len(k) < 3 or len(d) < 3 or len(j) < 3:
                return
            
            # KDJ 金叉条件
            k_cross_up = k[-2] < d[-2] and k[-1] > d[-1]
            j_from_oversold = j[-2] < 20 and j[-1] >= 20
            low_position = k[-1] < 50 and d[-1] < 50
            
            if k_cross_up and j_from_oversold and low_position:
                ctx.buy_shares = ctx.calc_target_shares(percent)
                if ctx.buy_shares > 0:
                    entry_prices[symbol] = close_values[-1]
                print(f"KDJ买入信号: 买入股票 {symbol}")
        except Exception as e:
            print(f"分析股票 {symbol} 时出错: {e}")
    
    return kdj_strategy


def run_backtest(
    symbols=None,
    start_date="20240101",
    end_date="20250224",
    initial_cash=100000,
    percent=0.25,
    save_plot=True
):
    """运行 KDJ 策略回测"""
    import pybroker as pb
    from pybroker import Strategy
    from pybroker.ext.data import AKShare
    if symbols is None:
        symbols = ["603893", "002594", "002049", "600048"]
    
    akshare = AKShare()
    my_config = pb.StrategyConfig(initial_cash=initial_cash)
    strategy = Strategy(akshare, start_date=start_date, end_date=end_date, config=my_config)
    
    kdj_strategy = make_kdj_strategy(percent=percent)
    strategy.add_execution(fn=kdj_strategy, symbols=symbols)
    
    result = strategy.backtest()
    
    # 打印回测结果
    print("\n回测性能指标:")
    print(result.metrics_df.round(4))
    print("\n交易概览:")
    print(f"总交易次数: {len(result.trades)}")
    print(f"胜率: {result.metrics.win_rate:.2f}%")
    print(f"最大回撤: {result.metrics.max_drawdown_pct*100:.2f}%")
    print(f"总收益率: {result.metrics.total_return_pct:.2f}%")
    print(f"夏普比率: {result.metrics.sharpe:.4f}")
    
    # 绘制资金曲线
    plt.figure(figsize=(10, 6))
    plt.plot(result.portfolio.index, result.portfolio['equity'], label='Portfolio Equity')
    plt.title('Portfolio Equity Curve')
    plt.xlabel('Date')
    plt.ylabel('Equity')
    plt.legend()
    plt.grid(True)
    
    plot_path = 'equity_curve.png'
    plt.savefig(plot_path)
    print(f"\n资金曲线已保存: {plot_path}")
    plt.close()
    
    return result


if __name__ == "__main__":
    run_backtest()
