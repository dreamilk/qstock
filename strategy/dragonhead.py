import pandas as pd
import akshare as ak
from datetime import datetime, timedelta
from strategy.base import Strategy, Stock
from typing import List


class DragonHeadStrategy(Strategy):
    """龙回头策略 - 寻找涨停后回调企稳的股票"""
    
    def __init__(self, limit_up_threshold=7.0, pullback_min=-25, pullback_max=0, 
                 vol_increase_threshold=0.8, days_to_check=3):
        super().__init__(name="dragonhead")
        
        # 可配置的策略参数
        self.limit_up_threshold = limit_up_threshold  # 涨停阈值
        self.pullback_min = pullback_min  # 最小回调幅度
        self.pullback_max = pullback_max  # 最大回调幅度
        self.vol_increase_threshold = vol_increase_threshold  # 成交量放大阈值
        self.days_to_check = days_to_check  # 检查企稳的天数
        
    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10, filter_stocks: bool = True) -> List[Stock]:
        """
        根据龙回头策略筛选股票
        
        Args:
            buy_date: the date to buy the stock
            limit_stock_count: 返回的股票数量上限
            filter_stocks: 是否过滤创业板、科创板和ST股
        
        Returns:
            List of filtered stocks, sorted by score
        """
        # 转换日期为datetime对象
        buy_date_dt = datetime.strptime(buy_date, "%Y%m%d")
        
        # 获取20个交易日前的日期，用于分析
        start_date = (buy_date_dt - timedelta(days=40)).strftime("%Y-%m-%d")
        end_date = buy_date
        
        # 获取A股股票代码列表
        stock_list = ak.stock_zh_a_spot_em()
        
        # 结果列表
        scored_stocks = []
        
        # 遍历股票
        for _, row in stock_list.iterrows():
            stock_code = row['代码']
            stock_name = row['名称']

            # 过滤创业板、科创板、ST股
            if filter_stocks:
                # 允许主板、创业板、科创板
                if not stock_code.startswith('60') and not stock_code.startswith('00') and not stock_code.startswith('30') and not stock_code.startswith('68'):
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
                
                # 寻找涨停（使用参数化的涨停阈值）
                limit_up_days = hist_data[hist_data['涨跌幅'] >= self.limit_up_threshold].index.tolist()
                
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
                
                # 回调幅度在参数设定的范围之间
                if max_pullback < self.pullback_min or max_pullback > self.pullback_max:
                    continue
                
                # 判断企稳（最近3天K线呈现企稳趋势）
                recent_data = hist_data.iloc[-3:].copy()
                
                # 成交量放大
                vol_change = recent_data['成交量'].mean() / hist_data.iloc[-6:-3]['成交量'].mean()
                
                # 价格趋势，放宽为不要求上涨，只要不是明显下跌
                price_trend = recent_data['收盘'].pct_change().mean() > -0.02
                
                # 计算技术指标
                hist_data['MA5'] = hist_data['收盘'].rolling(5).mean()
                hist_data['MA10'] = hist_data['收盘'].rolling(10).mean()
                hist_data['MA20'] = hist_data['收盘'].rolling(20).mean()
                
                # 计算MACD
                hist_data['EMA12'] = hist_data['收盘'].ewm(span=12).mean()
                hist_data['EMA26'] = hist_data['收盘'].ewm(span=26).mean()
                hist_data['DIFF'] = hist_data['EMA12'] - hist_data['EMA26']
                hist_data['DEA'] = hist_data['DIFF'].ewm(span=9).mean()
                hist_data['MACD'] = 2 * (hist_data['DIFF'] - hist_data['DEA'])
                
                # 计算RSI
                delta = hist_data['收盘'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                hist_data['RSI'] = 100 - (100 / (1 + rs))
                
                # 添加更多技术指标信号判断
                ma_trend = recent_data['MA5'].iloc[-1] > recent_data['MA10'].iloc[-1] or hist_data['MA5'].iloc[-1] > hist_data['MA5'].iloc[-2]
                macd_signal = hist_data['MACD'].iloc[-1] > hist_data['MACD'].iloc[-2] or hist_data['MACD'].iloc[-1] > 0
                rsi_signal = 20 < hist_data['RSI'].iloc[-1] < 80 and hist_data['RSI'].iloc[-1] > hist_data['RSI'].iloc[-3]
                
                if vol_change > self.vol_increase_threshold and price_trend and (ma_trend or macd_signal or rsi_signal):
                    # 计算股票得分
                    score = self._calculate_score(
                        max_pullback=max_pullback,
                        vol_change=vol_change,
                        price_trend=recent_data['收盘'].pct_change().mean() * 100,
                        days_since_limit_up=len(hist_data) - 1 - latest_limit_up,
                        limit_up_strength=hist_data.iloc[latest_limit_up]['涨跌幅'],
                        recent_close_prices=recent_data['收盘'].tolist(),
                        recent_volumes=recent_data['成交量'].tolist(),
                        stock_code=stock_code
                    )
                    
                    # 计算所有需要的值
                    current_price = float(hist_data.iloc[-1]['收盘'])
                    buy_price = float(hist_data.iloc[-1]['收盘'])
                    
                    # 使用波动率设置止损点和止盈点
                    recent_volatility = hist_data['涨跌幅'].tail(20).std()
                    stop_loss = round(buy_price * (1 - 2 * recent_volatility/100), 2)  # 止损价格
                    sell_price = round(buy_price * (1 + 3 * recent_volatility/100), 2)  # 止盈价格

                    # 计算风险收益比
                    risk_reward_ratio = (sell_price - buy_price) / (buy_price - stop_loss)

                    # 风险收益比要求放宽
                    if risk_reward_ratio > 1.2:
                        # 创建Stock对象并添加到结果列表
                        stock = Stock()
                        stock.code = stock_code
                        stock.name = stock_name
                        stock.current_price = current_price
                        stock.buy_price = buy_price
                        stock.sell_price = sell_price
                        stock.suggest_reason = f"龙回头策略：该股票在{hist_data.index[latest_limit_up]}涨停，随后回调{max_pullback:.2f}%，目前已企稳回升，成交量放大{vol_change:.2f}倍，风险收益比{risk_reward_ratio:.2f}，评分: {score:.2f}"
                        stock.score = score
                        scored_stocks.append(stock)
                
            except Exception as e:
                # 跳过出错的股票
                continue
        
        # 按评分排序并返回前N个
        result_stocks = sorted(scored_stocks, key=lambda x: x.score, reverse=True)[:limit_stock_count]
        return result_stocks
    
    def _calculate_score(self, max_pullback, vol_change, price_trend, days_since_limit_up, 
                         limit_up_strength, recent_close_prices, recent_volumes, stock_code=None):
        """
        计算龙回头策略的股票评分
        
        Args:
            max_pullback: 最大回调幅度(%)
            vol_change: 成交量变化倍数
            price_trend: 最近价格趋势(%)
            days_since_limit_up: 距离涨停天数
            limit_up_strength: 涨停当天涨幅
            recent_close_prices: 最近几天收盘价列表
            recent_volumes: 最近几天成交量列表
            stock_code: 股票代码
            
        Returns:
            综合评分(0-100)
        """
        score = 0
        
        # 1. 回调评分 (理想回调-10%左右，距离-10%越远评分越低)
        pullback_score = 30 - abs(max_pullback + 10) * 3
        pullback_score = max(0, min(30, pullback_score))
        
        # 2. 成交量评分 (成交量放大程度越高越好)
        volume_score = min(25, vol_change * 10)
        
        # 3. 价格趋势评分 (上涨趋势越强越好)
        trend_score = min(20, price_trend * 4)
        
        # 4. 最近性评分 (距离涨停天数越少越好，最高15天)
        recency_score = max(0, 15 - days_since_limit_up)
        
        # 5. 涨停强度评分
        strength_score = min(10, (limit_up_strength - 9.5) * 2)
        
        # 计算总分
        score = pullback_score + volume_score + trend_score + recency_score + strength_score
        
        # 额外奖励: 如果最近3天形成明显的上升通道
        if len(recent_close_prices) >= 3 and recent_close_prices[0] < recent_close_prices[1] < recent_close_prices[2]:
            score += 5
        
        # 额外奖励: 如果最近成交量持续放大
        if len(recent_volumes) >= 3 and recent_volumes[0] < recent_volumes[1] < recent_volumes[2]:
            score += 5
            
        # 行业板块分析加分
        try:
            # 获取当前热门行业
            hot_sectors = self._get_hot_sectors()
            stock_sector = self._get_stock_sector(stock_code)
            
            if stock_sector in hot_sectors:
                # 热门行业加分
                score += 10
        except:
            pass
        
        return score 

    def _get_hot_sectors(self):
        """获取当日热门行业"""
        try:
            sector_data = ak.stock_sector_spot_em()
            # 按涨跌幅排序，取前5名
            hot_sectors = sector_data.sort_values(by='涨跌幅', ascending=False).head(5)['板块名称'].tolist()
            return hot_sectors
        except:
            return []
        
    def _get_stock_sector(self, stock_code):
        """获取股票所属行业"""
        try:
            # 可以使用akshare获取股票所属行业
            # 这里只是示例，具体实现可能需要根据akshare的API调整
            stock_info = ak.stock_individual_info_em(symbol=stock_code)
            if '所属行业' in stock_info.index:
                return stock_info.loc['所属行业', 'value']
            return None
        except:
            return None 
