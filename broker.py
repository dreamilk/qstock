# 导入所需的库和模块
import pybroker as pb
from pybroker import Strategy, ExecContext, highest, lowest
from pybroker.ext.data import AKShare
import akshare as ak
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# 瑞芯微 603893
# 比亚迪 002594
# 紫光国微 002049
# 保利发展 600048

# 设置回测时间为2024年1月到2025年2月
start_date = "20240101"
end_date = "20250224"

# 由于我们将使用动态选股策略，可以考虑使用更大的股票池
symbols = ["603893", "002594", "002049", "600048"]

percent = 0.25  # 单只股票使用资金比例
initial_cash = 100000

# 初始化 AKShare 数据源
akshare = AKShare()

# 全局字典用于跟踪每个股票的买入价格
entry_prices = {}

# 定义交易策略：使用KDJ指标买入，设置止损和止盈条件
def kdj_strategy(ctx: ExecContext):
    global entry_prices
    symbol = ctx.symbol
    pos = ctx.long_pos()
    
    # 如果有持仓，检查是否需要卖出
    if pos:
        # 使用手动跟踪的入场价格
        if symbol in entry_prices:
            entry_price = entry_prices[symbol]
            current_price = ctx.close[-1]
            
            # 计算当前收益率
            current_return = (current_price - entry_price) / entry_price * 100
            
            # 止损条件：亏损超过5%
            if current_return < -5:
                ctx.sell_shares = pos.shares
                print(f"止损卖出 {symbol}，持有天数: {pos.bars}，收益率: {current_return:.2f}%")
                # 卖出后移除记录
                if ctx.sell_shares == pos.shares:
                    entry_prices.pop(symbol, None)
                return
                
            # 止盈条件：收益超过10%
            if current_return > 10:
                ctx.sell_shares = pos.shares
                print(f"止盈卖出 {symbol}，持有天数: {pos.bars}，收益率: {current_return:.2f}%")
                # 卖出后移除记录
                if ctx.sell_shares == pos.shares:
                    entry_prices.pop(symbol, None)
                return
                
            # 最大持有天数条件：超过5天强制卖出
            if pos.bars >= 5:
                ctx.sell_shares = pos.shares
                print(f"持有时间到期卖出 {symbol}，持有天数: {pos.bars}，收益率: {current_return:.2f}%")
                # 卖出后移除记录
                if ctx.sell_shares == pos.shares:
                    entry_prices.pop(symbol, None)
                return
            
            # 其他出场条件：连续2天下跌且跌幅超过3%
            if len(ctx.close) >= 3:
                pct_change_1 = (ctx.close[-1] - ctx.close[-2]) / ctx.close[-2] * 100
                pct_change_2 = (ctx.close[-2] - ctx.close[-3]) / ctx.close[-3] * 100
                if pct_change_1 < 0 and pct_change_2 < 0 and (pct_change_1 + pct_change_2) < -3:
                    ctx.sell_shares = pos.shares
                    print(f"连续下跌卖出 {symbol}，持有天数: {pos.bars}，收益率: {current_return:.2f}%")
                    # 卖出后移除记录
                    if ctx.sell_shares == pos.shares:
                        entry_prices.pop(symbol, None)
                    return
        else:
            print(f"警告: 无法找到 {symbol} 的入场价格记录，跳过卖出判断")
    
    # 买入逻辑改为KDJ策略
    try:
        close_values = ctx.close
        high_values = ctx.high
        low_values = ctx.low
        
        # 确保有足够的历史数据
        if len(close_values) < 14:  # KDJ通常需要9-14天的数据
            return
        
        # 计算KDJ指标 (9日)
        k, d, j = calculate_kdj(close_values, high_values, low_values, n=9)
        
        # 如果数据不足，则返回
        if len(k) < 3 or len(d) < 3 or len(j) < 3:
            return
        
        # KDJ金叉条件1: K线上穿D线
        k_cross_up = k[-2] < d[-2] and k[-1] > d[-1]
        
        # KDJ金叉条件2: J线从超卖区域(<20)向上突破
        j_from_oversold = j[-2] < 20 and j[-1] >= 20
        
        # 条件3: K值和D值都处在低位区域(小于50)，表明趋势从弱转强
        low_position = k[-1] < 50 and d[-1] < 50
        
        # 买入信号: 同时满足上述条件
        if k_cross_up and j_from_oversold and low_position:
            # 符合所有条件，买入
            ctx.buy_shares = ctx.calc_target_shares(percent)
            # 记录买入价格
            if ctx.buy_shares > 0:
                entry_prices[symbol] = close_values[-1]  # 使用当前收盘价作为入场价格
            print(f"KDJ买入信号: 买入股票 {symbol}")
        
    except Exception as e:
        print(f"分析股票 {symbol} 时出错: {e}")

# 计算KDJ指标函数
def calculate_kdj(close, high, low, n=9):
    # 获取周期内的最高价和最低价
    highest_high = np.array([max(high[max(0, i-n+1):i+1]) for i in range(len(high))])
    lowest_low = np.array([min(low[max(0, i-n+1):i+1]) for i in range(len(low))])
    
    # 计算RSV
    rsv = np.zeros_like(close)
    for i in range(len(close)):
        if highest_high[i] == lowest_low[i]:
            rsv[i] = 50  # 如果最高价等于最低价，RSV设为50
        else:
            rsv[i] = 100 * (close[i] - lowest_low[i]) / (highest_high[i] - lowest_low[i])
    
    # 初始化K、D值
    k = np.zeros_like(close)
    d = np.zeros_like(close)
    
    # 第一个值初始化为50
    k[0] = 50
    d[0] = 50
    
    # 计算K值、D值
    for i in range(1, len(close)):
        k[i] = 2/3 * k[i-1] + 1/3 * rsv[i]
        d[i] = 2/3 * d[i-1] + 1/3 * k[i]
    
    # 计算J值
    j = 3 * k - 2 * d
    
    return k, d, j

# 创建策略配置，初始资金为 100000
my_config = pb.StrategyConfig(initial_cash=initial_cash)

# 使用配置、数据源、起始日期、结束日期，以及刚才定义的交易策略创建策略对象
strategy = Strategy(akshare, start_date=start_date, end_date=end_date, config=my_config)

# 添加执行策略，设置股票代码和要执行的函数
strategy.add_execution(
    fn=kdj_strategy, 
    symbols=symbols
)

# 执行回测，并打印出回测结果的度量值
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

# 绘制结果图表
plt.figure(figsize=(10, 6))
plt.plot(result.portfolio.index, result.portfolio['equity'], label='Portfolio Equity')
plt.title('Portfolio Equity Curve')
plt.xlabel('Date')
plt.ylabel('Equity')
plt.legend()
plt.grid(True)
plt.savefig('equity_curve.png')  # 保存为图片文件
plt.show()