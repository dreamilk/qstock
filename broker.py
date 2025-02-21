# 导入所需的库和模块
import pybroker as pb
from pybroker import Strategy, ExecContext, highest
from pybroker.ext.data import AKShare
import akshare as ak
import matplotlib.pyplot as plt

# 瑞芯微 603893
# 比亚迪 002594
# 紫光国微 002049
# 保利发展 600048

symbols = ["603893","002594","002049","600048"]
percent = 1
stop_loss_pct = 10
stop_profit_pct = 10
initial_cash=100000
start_date = "20240101"
end_date = "20250221"


d = ak.stock_zh_a_spot_em()
for symbol in symbols:
    print(d[(d["代码"]==symbol)])

# 初始化 AKShare 数据源
akshare = AKShare()


# 定义交易策略：如果当前没有持有该股票，则买入股票，并设置止盈点位
def buy_with_stop_loss(ctx: ExecContext):
    pos = ctx.long_pos()
    if not pos:
        ctx.buy_shares = ctx.calc_target_shares(percent)
        ctx.hold_bars = 100
    else:
        high_10d = ctx.indicator('high_10d')
        print(high_10d)
        ctx.sell_shares = pos.shares
        ctx.stop_profit_pct = stop_profit_pct



# 创建策略配置，初始资金为 100000
my_config = pb.StrategyConfig(initial_cash=initial_cash)
# 使用配置、数据源、起始日期、结束日期，以及刚才定义的交易策略创建策略对象
strategy = Strategy(akshare, start_date=start_date, end_date=end_date, config=my_config)
# 添加执行策略，设置股票代码和要执行的函数
strategy.add_execution(fn=buy_with_stop_loss, symbols=symbols, indicators=[highest('high_10d', 'close', period=10)])
# 执行回测，并打印出回测结果的度量值（四舍五入到小数点后四位）
result = strategy.backtest()


print(result.portfolio.index)
# print(result.metrics_df.round(4))
# print(result.metrics)
# print(result.orders)
# print(result.positions)
# print(result.trades)

# 在回测结果后添加以下代码
plt.figure(figsize=(10, 6))
plt.plot(result.portfolio.index, result.portfolio['equity'], label='Portfolio Equity')
plt.title('Portfolio Equity Curve')
plt.xlabel('Date')
plt.ylabel('Equity')
plt.legend()
plt.grid(True)
plt.savefig('equity_curve.png')  # 保存为图片文件