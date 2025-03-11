from strategy.base import Strategy, Stock
from typing import List
import akshare as ak
import datetime
import pandas as pd

class CustomStrategy(Strategy):
    def __init__(self):
        super().__init__(name="custom")
        
        
    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10, filter_stocks: bool = True) -> List[Stock]:

        # 获取所有股票代码
        all_stocks = ak.stock_zh_a_spot_em()

        # 存储符合条件的股票
        stocks = []
        
        # 将日期字符串转换为datetime对象以进行日期计算
        buy_date_obj = datetime.datetime.strptime(buy_date, "%Y%m%d")
        
        # 计算开始日期（需要获取buy_date之前的5天数据以进行分析）
        start_date_obj = buy_date_obj - datetime.timedelta(days=10)  # 多取几天以确保有足够的交易日
        start_date = start_date_obj.strftime("%Y%m%d")
        
        for _, row in all_stocks.iterrows():  # 限制处理的股票数量以提高效率
            code = row['代码']
            stock_name = row['名称']

            # 过滤创业板、科创板、ST股
            if filter_stocks:
                if not code.startswith('60') and not code.startswith('00'):
                    continue
                if 'ST' in stock_name:
                    continue

            print(f"正在处理股票: {code}, {stock_name}")

            try:
                # 获取股票的主力持股数据
                main_funds_data = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
                # 确保有足够的主力资金数据
                if len(main_funds_data) < 5:
                    continue

                # 计算近期主力资金流入情况
                main_funds_data = main_funds_data.sort_values(by="日期", ascending=False).reset_index(drop=True)
                
                # 获取历史数据
                stock_data = ak.stock_zh_a_hist(symbol=code, start_date=start_date, end_date=buy_date, adjust="qfq")
                
                # 确保有足够的数据
                if len(stock_data) < 5:
                    continue
                
                # 按日期降序排序，使索引0为最近日期
                stock_data = stock_data.sort_values(by="日期", ascending=False).reset_index(drop=True)
                
                # 条件1: 3日前涨，近两日跌
                day3_up = stock_data.iloc[3]['涨跌幅'] > 0
                day2_down = stock_data.iloc[2]['涨跌幅'] < 0
                day1_down = stock_data.iloc[1]['涨跌幅'] < 0
                
                # 条件2: 3日前成交量大于4日前
                day3_volume_higher = stock_data.iloc[3]['成交量'] > stock_data.iloc[4]['成交量']
                
                # 条件3: 3日前最低价高于特定价格点 (这里假设为5元，根据实际需求调整)
                price_threshold = 5.0
                day3_low_price_higher = stock_data.iloc[3]['最低'] > price_threshold
                
                # 条件4: 前一天收盘价低于4日前收盘价
                day1_close_lower_than_day4 = stock_data.iloc[1]['收盘'] < stock_data.iloc[4]['收盘']

                # 条件5: 最近一天有主力资金净流入
                recent_main_fund_inflow = main_funds_data.iloc[1]['主力净流入-净额'] > 0

                # 条件6: 近三天主力资金净流入为正
                recent_days_inflow = sum(main_funds_data.iloc[1:3]['主力净流入-净额'])
                recent_main_fund_inflow_3_days = recent_days_inflow > 0

                
                # 检查所有条件
                # 1. 3日前涨，近两日跌
                # 2. 3日前成交量大于4日前
                # 3. 3日前最低价高于特定价格点
                # 4. 前一天收盘价低于4日前收盘价
                # 5. 最近一天有主力资金净流入
                # 6. 近三天主力资金净流入为正
                if (day3_up and day2_down and day1_down and 
                    day3_volume_higher and day3_low_price_higher and 
                    day1_close_lower_than_day4 and recent_main_fund_inflow and recent_main_fund_inflow_3_days):

                    # 创建Stock对象并添加到结果列表
                    stock_name = all_stocks.loc[all_stocks['代码'] == code, '名称'].values[0] if not all_stocks.empty else "Unknown"
                    stock = Stock()
                    stock.code = code
                    stock.name = stock_name
                    stock.current_price = float(stock_data.iloc[0]['收盘'])
                    stock.buy_price = float(stock_data.iloc[0]['收盘'])
                    stock.sell_price = round(stock.buy_price * 1.07, 2)  # 设置7%的获利目标
                    stock.suggest_reason = f"自定义策略：该股票在{buy_date}满足所有条件"
                    stocks.append(stock)
                    
                    # 如果已经找到足够的股票，则停止
                    if len(stocks) >= limit_stock_count:
                        break
                        
            except Exception as e:
                print(f"Error processing stock {code}: {e}")
                continue

        return stocks
