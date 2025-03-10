import pandas as pd
import akshare as ak
from datetime import datetime, timedelta
from strategy.base import Strategy, Stock
from typing import List


class DragonHeadStrategy(Strategy):
    """龙回头策略 - 寻找涨停后回调企稳的股票"""
    
    def __init__(self):
        super().__init__(name="dragonhead")
        
    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10, filter_stocks: bool = True) -> List[Stock]:
        """
        根据龙回头策略筛选股票
        
        Args:
            buy_date: the date to buy the stock
        
        Returns:
            List of filtered stocks
        """
        # 转换日期为datetime对象
        buy_date_dt = datetime.strptime(buy_date, "%Y%m%d")
        
        # 获取20个交易日前的日期，用于分析
        start_date = (buy_date_dt - timedelta(days=40)).strftime("%Y-%m-%d")
        end_date = buy_date
        
        # 获取A股股票代码列表
        stock_list = ak.stock_zh_a_spot_em()
        
        # 结果列表
        result_stocks = []
        
        # 遍历股票
        for _, row in stock_list.iterrows():
            stock_code = row['代码']
            stock_name = row['名称']

            # 过滤创业板、科创板、ST股
            if filter_stocks:
                if not stock_code.startswith('60') and not stock_code.startswith('00'):
                    continue
                if 'ST' in stock_name:
                    continue

            print(f"正在处理股票: {stock_code} {stock_name}")

            try:
                # 获取历史行情数据
                hist_data = ak.stock_zh_a_hist(symbol=stock_code, start_date=start_date, end_date=end_date, adjust="qfq")
                
                if len(hist_data) < 10:
                    continue
                
                # 计算涨跌幅
                hist_data['涨跌幅'] = hist_data['收盘'].pct_change() * 100
                
                # 寻找涨停（这里假设涨停为9.5%以上）
                limit_up_days = hist_data[hist_data['涨跌幅'] >= 9.5].index.tolist()
                
                if not limit_up_days:
                    continue
                
                # 从最近的涨停日开始分析
                latest_limit_up = limit_up_days[-1]
                
                # 确保涨停后至少有3个交易日
                if latest_limit_up >= len(hist_data) - 3:
                    continue
                
                # 获取涨停后的数据
                post_limit_data = hist_data.iloc[latest_limit_up+1:].copy()
                
                # 判断是否回调
                max_pullback = (post_limit_data['收盘'].min() - hist_data.iloc[latest_limit_up]['收盘']) / hist_data.iloc[latest_limit_up]['收盘'] * 100
                
                # 回调幅度在-15%到-5%之间
                if max_pullback < -15 or max_pullback > -5:
                    continue
                
                # 判断企稳（最近3天K线呈现企稳趋势）
                recent_data = hist_data.iloc[-3:].copy()
                
                # 成交量放大
                vol_change = recent_data['成交量'].mean() / hist_data.iloc[-6:-3]['成交量'].mean()
                
                # 近3日K线实体越来越大，且收盘价上涨
                price_trend = recent_data['收盘'].pct_change().mean() > 0
                
                if vol_change > 1.1 and price_trend:
                    # 创建Stock对象并添加到结果列表
                    stock = Stock()
                    stock.code = stock_code
                    stock.name = stock_name
                    stock.current_price = float(hist_data.iloc[-1]['收盘'])
                    stock.buy_price = float(hist_data.iloc[-1]['收盘'])
                    stock.sell_price = round(stock.buy_price * 1.15, 2)  # 设置15%的获利目标
                    stock.suggest_reason = f"龙回头策略：该股票在{hist_data.index[latest_limit_up]}涨停，随后回调{max_pullback:.2f}%，目前已企稳回升，成交量放大{vol_change:.2f}倍"
                    
                    result_stocks.append(stock)

                    if len(result_stocks) >= limit_stock_count:
                        break
                
            except Exception as e:
                # 跳过出错的股票
                continue
        
        return result_stocks 
