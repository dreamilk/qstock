from strategy.base import Stock, Strategy
from typing import List
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

class HitBoardStrategy(Strategy):
    def __init__(self):
        super().__init__(name="hit_board")

    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10, filter_stocks: bool = True) -> List[Stock]:
        """
        Filter stocks based on hit board strategy
        
        Args:
            buy_date: the date to buy the stock
        
        Returns:
            List of stocks that hit the upper price limit on the previous trading day
            and meet additional filtering criteria
        """
        # Convert date format if needed
        buy_date_dt = datetime.strptime(buy_date, "%Y%m%d")
        
        # Get trading calendar to find the previous trading day
        trading_calendar = ak.tool_trade_date_hist_sina()
        trading_days = trading_calendar["trade_date"].tolist()
        
        # Convert buy_date_formatted to date object for proper comparison
        buy_date_obj = buy_date_dt.date()
        trading_days = [day for day in trading_days if day <= buy_date_obj]
        
        if len(trading_days) < 2:
            return []  # Not enough trading history
            
        # Get actual previous trading day
        prev_date_formatted = trading_days[-2].strftime("%Y-%m-%d")  # Convert date object back to string
        
        # Get data range for analysis (10 days prior)
        start_date = (buy_date_dt - timedelta(days=20)).strftime("%Y-%m-%d")
        end_date = buy_date_dt.strftime("%Y-%m-%d")
        
        # Get all A-share stocks
        stock_list = ak.stock_zh_a_spot_em()
        
        filtered_stocks = []
        
        # Process each stock
        for _, row in stock_list.iterrows():
            stock_code = row['代码']
            stock_name = row['名称']

            # 过滤创业板、科创板、ST股
            if filter_stocks:
                if not stock_code.startswith('60') and not stock_code.startswith('00'):
                    continue
                if 'ST' in stock_name:
                    continue

            print(f"Processing stock: {stock_code} {stock_name}")
            
            try:
                # Get historical data
                hist_data = ak.stock_zh_a_hist(symbol=stock_code, start_date=start_date, end_date=end_date, adjust="qfq")
                
                if len(hist_data) < 6:  # Need at least 6 days of data
                    continue
                
                # Calculate daily percentage change
                hist_data['涨跌幅'] = hist_data['收盘'].pct_change() * 100
                
                # Check if the stock hit upper limit on the previous trading day
                # For most stocks it's 10%, for ST stocks it's 5%
                limit_percentage = 5.0 if "ST" in stock_name else 10.0
                
                # Get previous day data
                prev_day_data = hist_data[hist_data['日期'] == prev_date_formatted]
                if prev_day_data.empty:
                    continue
                
                # Check if hit upper limit
                day_before_prev = hist_data[hist_data['日期'] < prev_date_formatted].iloc[-1]
                limit_price = round(day_before_prev['收盘'] * (1 + limit_percentage / 100), 2)
                
                if prev_day_data.iloc[0]['收盘'] < limit_price:
                    continue  # Not hit upper limit
                
                # Check if maintained until close (close equals high)
                if prev_day_data.iloc[0]['收盘'] != prev_day_data.iloc[0]['最高']:
                    continue  # Not maintained until close
                
                # Check for volume increase
                prev_5_days = hist_data.iloc[-6:-1]
                avg_volume = prev_5_days['成交量'].mean()
                current_volume = prev_day_data.iloc[0]['成交量']
                
                if current_volume <= avg_volume * 1.5:
                    continue  # Volume not increased significantly
                
                # Create Stock object for filtered stock
                stock = Stock()
                stock.code = stock_code
                stock.name = stock_name
                stock.current_price = float(hist_data.iloc[-1]['收盘'])
                stock.buy_price = float(hist_data.iloc[-1]['收盘'])
                stock.sell_price = round(stock.buy_price * 1.1, 2)  # 10% profit target
                
                # Calculate how long the stock maintained the limit (approximation)
                limit_hit_description = "涨停"
                if current_volume > avg_volume * 3:
                    limit_hit_description = "强势涨停，成交量放大超3倍"
                elif current_volume > avg_volume * 2:
                    limit_hit_description = "强势涨停，成交量放大超2倍"
                
                stock.suggest_reason = f"涨停板策略：该股票在{prev_date_formatted}{limit_hit_description}，且维持到收盘，成交量是过去5日均量的{current_volume/avg_volume:.2f}倍"
                
                filtered_stocks.append(stock)
                
                if len(filtered_stocks) >= limit_stock_count:
                    break

            except Exception as e:
                print(f"Error processing {stock_code}: {e}")
                continue
        
        # Sort stocks by criteria (could sort by volume increase ratio for example)
        filtered_stocks.sort(key=lambda s: float(s.suggest_reason.split('均量的')[1].split('倍')[0]), reverse=True)
        
        return filtered_stocks