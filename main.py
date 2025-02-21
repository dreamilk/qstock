import akshare as ak
import mplfinance as mpf  # Please install mplfinance as follows: pip install mplfinance


symbol = "603893"

stock_zh_a_hist_df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date="20170301", end_date='20231022', adjust="")
print(stock_zh_a_hist_df)
