from strategy.base import Strategy, Stock
from typing import List
import akshare as ak
import datetime
import pandas as pd
import sys
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class CustomStrategy(Strategy):
    def __init__(self):
        super().__init__(name="custom")
        
    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10, filter_stocks: bool = True) -> List[Stock]:        
        try:
            # 获取最近一段时间的交易日历
            trade_date_df = ak.tool_trade_date_hist_sina()
            trade_dates = [str(date).replace("-", "") for date in trade_date_df["trade_date"].tolist()]
            trade_dates = sorted(trade_dates, reverse=True)
            
            # 找出buy_date之前的交易日
            recent_dates = [date for date in trade_dates if date <= buy_date]
            
            if len(recent_dates) <= 4:
                print("无法获取足够的交易日数据")
                return []
                
            # 获取相关交易日期
            date_4days_ago = recent_dates[4]  # 4个交易日前（涨停日）
            date_3days_ago = recent_dates[3]  # 3个交易日前（需为上涨，成交量需大于涨停日）
            date_2days_ago = recent_dates[2]  # 2个交易日前（需为下跌）
            date_1day_ago = recent_dates[1]   # 1个交易日前（需为下跌）
            latest_date = recent_dates[0]     # 最近交易日
            
            print(f"将获取 {date_4days_ago} 的涨停股票数据...")
            
            # 获取涨停股票数据
            limit_up_stocks = ak.stock_zt_pool_em(date=date_4days_ago)
            
            if limit_up_stocks.empty:
                print(f"{date_4days_ago} 没有涨停股票数据")
                return []
            
            print(f"成功获取数据，共 {len(limit_up_stocks)} 条记录")
            
            # 筛选沪深主板股票
            if filter_stocks:
                main_board_stocks = limit_up_stocks[
                    (limit_up_stocks['代码'].str.startswith('00') | 
                     limit_up_stocks['代码'].str.startswith('60'))
                ]
                
                # 排除ST股票
                filtered_stocks = main_board_stocks[~main_board_stocks['名称'].str.contains('ST')]
                print(f"筛选后股票数: {len(filtered_stocks)}")
            else:
                filtered_stocks = limit_up_stocks
            
            # 存储符合条件的股票
            stocks = []
            
            for idx, stock_info in filtered_stocks.iterrows():
                stock_code = stock_info['代码']
                stock_name = stock_info['名称']
                
                print(f"正在处理股票: {stock_code}, {stock_name}")
                
                try:
                    # 获取股票历史数据
                    stock_hist = ak.stock_zh_a_hist(symbol=stock_code, period="daily", 
                                                   start_date=date_4days_ago, end_date=latest_date, 
                                                   adjust="qfq")
                    
                    # 检查数据是否完整
                    if len(stock_hist) < 5:  # 需要5个交易日的数据
                        continue
                    
                    # 检查日期是否匹配
                    dates_in_hist = [d.replace("-", "") for d in stock_hist['日期'].astype(str)]
                    
                    if not all(date in dates_in_hist for date in [date_4days_ago, date_3days_ago, date_2days_ago, date_1day_ago]):
                        continue
                    
                    # 获取涨停日和次日的成交量
                    volume_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['成交量'].values[0]
                    volume_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['成交量'].values[0]
                    
                    # 获取各日期的涨跌幅
                    pct_chg_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['涨跌幅'].values[0]
                    pct_chg_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['涨跌幅'].values[0]
                    pct_chg_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['涨跌幅'].values[0]
                    
                    # 获取4日前(涨停日)的最高价和最低价
                    high_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['最高'].values[0]
                    low_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['最低'].values[0]
                    
                    # 计算特定价格点：4日前最低价+(最高价-最低价)*0.3
                    price_point = low_4days_ago + (high_4days_ago - low_4days_ago) * 0.2
                    
                    # 获取3日前的最低价
                    low_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['最低'].values[0]
                    
                    # 获取最新收盘价
                    latest_close = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == latest_date]['收盘'].values[0]
                    
                    # 检查所有条件：
                    # 1. 3日前涨，近两日跌
                    # 2. 3日前成交量大于4日前
                    # 3. 3日前最低价高于特定价格点
                    if (pct_chg_3days_ago > 0 and 
                        pct_chg_2days_ago < 0 and 
                        pct_chg_1day_ago < 0 and
                        volume_3days_ago > volume_4days_ago):
                        
                        # 计算成交量变化率
                        volume_change_ratio = (volume_3days_ago / volume_4days_ago - 1) * 100
                        
                        # 计算价格条件满足的程度
                        price_condition_ratio = ((low_3days_ago - price_point) / low_4days_ago) * 100
                        
                        # 创建Stock对象并添加到结果列表
                        stock = Stock()
                        stock.code = stock_code
                        stock.name = stock_name
                        stock.current_price = float(latest_close)
                        stock.buy_price = float(latest_close)
                        stock.sell_price = round(stock.buy_price * 1.07, 2)  # 设置7%的获利目标
                        # 添加得分属性，根据成交量变化和价格条件计算
                        stock.score = round(volume_change_ratio * 0.6 + price_condition_ratio * 0.4, 2)
                        stock.suggest_reason = (f"自定义策略：涨停回调买入。{date_4days_ago}涨停，{date_3days_ago}上涨(+{pct_chg_3days_ago:.2f}%)，"
                                              f"成交量增加{volume_change_ratio:.2f}%，近两日回调，价格条件超额{price_condition_ratio:.2f}%")
                        stocks.append(stock)
                                                
                    
                except Exception as e:
                    print(f"处理股票 {stock_code} 时出错: {e}")
                    continue
            
            # 根据得分排序
            stocks.sort(key=lambda x: x.score, reverse=True)
            if len(stocks) > limit_stock_count:
                stocks = stocks[:limit_stock_count]
            return stocks
                
        except Exception as e:
            print(f"程序执行出错: {e}")
            return []
