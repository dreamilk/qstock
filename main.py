import akshare as ak
import mplfinance as mpf  # Please install mplfinance as follows: pip install mplfinance
import pandas as pd


# 列出a股所有股票
d = ak.stock_zh_a_spot_em()
print(d)

# 瑞芯微 603893
# 春秋航空 601021
symbol = "603893"

stock_zh_a_hist_df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date="20250101", end_date='20250224', adjust="")
print(stock_zh_a_hist_df)

# 将日期列转换为DatetimeIndex并设置为索引
stock_zh_a_hist_df['日期'] = pd.to_datetime(stock_zh_a_hist_df['日期'])
stock_zh_a_hist_df.set_index('日期', inplace=True)

# 将中文列名转换为英文列名
stock_zh_a_hist_df = stock_zh_a_hist_df.rename(columns={
    '开盘': 'Open',
    '最高': 'High',
    '最低': 'Low',
    '收盘': 'Close',
    '成交量': 'Volume'
})

# 绘制k线图并直接保存为图片
mpf.plot(stock_zh_a_hist_df, type='candle', mav=(5, 10, 20), volume=True, style='yahoo', savefig='kline.png')

# 获取分时数据
stock_zh_a_hist_pre_min_em_df = ak.stock_zh_a_hist_pre_min_em(symbol=symbol, start_time="09:00:00", end_time="15:00:00")
print(stock_zh_a_hist_pre_min_em_df)

# 保存csv
stock_zh_a_hist_pre_min_em_df.to_csv('stock_zh_a_hist_pre_min_em.csv')

# 计算最低成交价、 最高成交价
low_price = stock_zh_a_hist_pre_min_em_df[stock_zh_a_hist_pre_min_em_df['成交额'] > 0]['最低'].min()
high_price = stock_zh_a_hist_pre_min_em_df[stock_zh_a_hist_pre_min_em_df['成交额'] > 0]['最高'].max()

print(f"最低成交价: {low_price}, 最高成交价: {high_price}")