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

percent = 0.2  # 单只股票使用资金比例
initial_cash = 100000

# 初始化 AKShare 数据源
akshare = AKShare()

# 定义交易策略：根据pick.py选股逻辑买入，次日卖出
def buy_with_stop_loss(ctx: ExecContext):
    symbol = ctx.symbol
    pos = ctx.long_pos()
    
    # 如果有持仓，检查是否需要卖出
    if pos:
        # 如果是昨天买入的，今天卖出
        if pos.bars == 1:
            ctx.sell_shares = pos.shares
            # 使用日期对象获取当前日期，而不是直接访问curr_date
            print(f"卖出股票 {symbol}，持有天数: {pos.bars}")
        return
    
    # 如果没有持仓，直接在执行上下文中实现选股逻辑
    try:
        # 获取历史数据
        # 尝试使用PyBroker正确的属性名
        if not hasattr(ctx, 'close'):
            # 如果没有直接的价格属性，尝试通过数据框属性访问
            if hasattr(ctx, 'data') and ctx.data is not None:
                df = ctx.data
                close_values = df['close'].values
                open_values = df['open'].values
                high_values = df['high'].values
                low_values = df['low'].values
                volume_values = df['volume'].values
            else:
                return  # 无法获取数据，退出
        else:
            # 直接从上下文对象获取价格数据
            close_values = ctx.close
            open_values = ctx.open
            high_values = ctx.high
            low_values = ctx.low
            volume_values = ctx.volume
        
        # 确保有足够的历史数据
        if len(close_values) < 5:
            return
        
        # 使用最近5天的数据
        closes = close_values[-5:]     # 最后5个收盘价
        opens = open_values[-5:]       # 最后5个开盘价
        highs = high_values[-5:]       # 最后5个最高价
        lows = low_values[-5:]         # 最后5个最低价
        volumes = volume_values[-5:]   # 最后5个成交量
        
        # 计算涨跌幅 (近4天)
        pct_changes = np.zeros(4)
        for i in range(4):
            pct_changes[i] = (closes[i+1] - closes[i]) / closes[i] * 100
        
        # 条件1: 第1天是涨停(暂定为涨幅>=9.5%)
        if pct_changes[0] < 9.5:
            return
        
        # 条件2: 第2天是上涨
        if pct_changes[1] <= 0:
            return
        
        # 条件3: 第2天成交量大于第1天
        if volumes[1] <= volumes[0]:
            return
        
        # 条件4: 第3天和第4天是下跌
        if pct_changes[2] >= 0 or pct_changes[3] >= 0:
            return
        
        # 条件5: 计算特定价格点：涨停日最低价+(最高价-最低价)*0.3
        price_point = lows[0] + (highs[0] - lows[0]) * 0.3
        
        # 条件6: 次日最低价高于特定价格点
        if lows[1] <= price_point:
            return
        
        # 符合所有条件，买入
        ctx.buy_shares = ctx.calc_target_shares(percent)
        print(f"买入股票 {symbol}")
        
    except Exception as e:
        print(f"分析股票 {symbol} 时出错: {e}")

# 创建策略配置，初始资金为 100000
my_config = pb.StrategyConfig(initial_cash=initial_cash)

# 使用配置、数据源、起始日期、结束日期，以及刚才定义的交易策略创建策略对象
strategy = Strategy(akshare, start_date=start_date, end_date=end_date, config=my_config)

# 添加执行策略，设置股票代码和要执行的函数
strategy.add_execution(
    fn=buy_with_stop_loss, 
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