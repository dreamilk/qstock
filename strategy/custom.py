from strategy.base import Strategy, Stock
from typing import List, Dict, Tuple, Optional
import akshare as ak
import datetime
import pandas as pd
import numpy as np
import sys
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from tqdm import tqdm

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CustomStrategy(Strategy):
    def __init__(self):
        super().__init__(name="custom")
        # 配置HTTP会话，增加重试机制
        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        # 策略参数配置
        self.config = {
            'volume_ratio_threshold': 1.3,  # 放宽成交量比例要求(从1.5降至1.3)
            'price_point_factor': 0.25,     # 调整价格点因子(从0.2升至0.25，更宽松)
            'max_pullback': 12,             # 放宽最大回调幅度(从10%到12%)
            'rsi_period': 14,               # RSI周期
            'macd_fast': 12,                # MACD快线
            'macd_slow': 26,                # MACD慢线
            'macd_signal': 9,               # MACD信号线
            'boll_period': 20,              # 布林带周期
            'boll_std': 2,                  # 布林带标准差
        }
        
    def _get_trade_dates(self, buy_date: str, days_needed: int = 5) -> List[str]:
        """获取交易日期列表"""
        trade_date_df = ak.tool_trade_date_hist_sina()
        trade_dates = [str(date).replace("-", "") for date in trade_date_df["trade_date"].tolist()]
        trade_dates = sorted(trade_dates, reverse=True)
        
        # 找出buy_date之前的交易日
        recent_dates = [date for date in trade_dates if date <= buy_date]
        
        if len(recent_dates) < days_needed:
            logger.error(f"无法获取足够的交易日数据，需要{days_needed}天，实际只有{len(recent_dates)}天")
            return []
            
        return recent_dates[:days_needed]
        
    def _calculate_score(self, 
                         volume_change_ratio: float, 
                         price_condition_ratio: float,
                         rsi_value: float = 50,
                         avg_downtrend_pct: float = 0,
                         macd_value: float = 0,
                         boll_position: float = 0.5) -> float:
        """计算股票综合得分"""
        # 权重分配: 成交量40%, 价格20%, RSI15%, 回调幅度10%, MACD10%, 布林带位置5%
        score = (volume_change_ratio * 0.4 + 
                price_condition_ratio * 0.2 + 
                (50 - rsi_value) * 0.15 +  # RSI值低更好(超卖)
                abs(avg_downtrend_pct) * 0.1 +  # 回调幅度更大更好
                macd_value * 0.1 +  # MACD底背离更好
                (1 - boll_position) * 0.05)  # 布林带底部更好
        return round(score, 2)
    
    def _calculate_technical_indicators(self, stock_hist: pd.DataFrame) -> Dict[str, float]:
        """计算多种技术指标（纯Python实现，不依赖TA-Lib）"""
        close_prices = stock_hist['收盘'].values
        high_prices = stock_hist['最高'].values
        low_prices = stock_hist['最低'].values
        volume = stock_hist['成交量'].values
        
        indicators = {}
        
        # 计算RSI
        if len(close_prices) >= self.config['rsi_period']:
            indicators['rsi'] = self._calculate_rsi(pd.Series(close_prices))
        else:
            indicators['rsi'] = 50
            
        # 计算MACD
        if len(close_prices) >= self.config['macd_slow'] + self.config['macd_signal']:
            macd_result = self._calculate_macd(pd.Series(close_prices))
            # MACD底部背离评分: 当MACD值为负但柱状图上升时为正向信号
            indicators['macd'] = 0
            if (macd_result['hist'][-1] > macd_result['hist'][-2] > macd_result['hist'][-3] and 
                macd_result['macd'][-1] < 0):
                indicators['macd'] = min(100, abs(macd_result['hist'][-1] - macd_result['hist'][-3]) * 100)
        else:
            indicators['macd'] = 0
                
        # 计算布林带位置
        if len(close_prices) >= self.config['boll_period']:
            boll_bands = self._calculate_bollinger_bands(pd.Series(close_prices))
            # 计算当前价格在布林带中的位置(0表示下轨，1表示上轨)
            current_close = close_prices[-1]
            band_width = boll_bands['upper'][-1] - boll_bands['lower'][-1]
            if band_width > 0:
                indicators['boll_position'] = (current_close - boll_bands['lower'][-1]) / band_width
            else:
                indicators['boll_position'] = 0.5
        else:
            indicators['boll_position'] = 0.5
            
        # 计算KDJ
        kdj = self._calculate_kdj(pd.Series(high_prices), pd.Series(low_prices), pd.Series(close_prices))
        indicators['k'] = kdj['k'][-1]
        indicators['d'] = kdj['d'][-1]
        indicators['j'] = kdj['j'][-1]
            
        return indicators
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """计算RSI指标"""
        delta = prices.diff().dropna()
        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        down = down.abs()
        
        avg_gain = up.rolling(window=period).mean()
        avg_loss = down.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    
    def _calculate_macd(self, prices: pd.Series) -> Dict[str, np.ndarray]:
        """计算MACD指标"""
        fast = prices.ewm(span=self.config['macd_fast'], adjust=False).mean()
        slow = prices.ewm(span=self.config['macd_slow'], adjust=False).mean()
        macd = fast - slow
        signal = macd.ewm(span=self.config['macd_signal'], adjust=False).mean()
        hist = macd - signal
        
        return {
            'macd': macd.values,
            'signal': signal.values,
            'hist': hist.values
        }
    
    def _calculate_bollinger_bands(self, prices: pd.Series) -> Dict[str, np.ndarray]:
        """计算布林带"""
        middle = prices.rolling(window=self.config['boll_period']).mean()
        std = prices.rolling(window=self.config['boll_period']).std()
        upper = middle + (std * self.config['boll_std'])
        lower = middle - (std * self.config['boll_std'])
        
        return {
            'upper': upper.values,
            'middle': middle.values,
            'lower': lower.values
        }
    
    def _calculate_kdj(self, high: pd.Series, low: pd.Series, close: pd.Series, 
                      n: int = 9, m1: int = 3, m2: int = 3) -> Dict[str, np.ndarray]:
        """计算KDJ指标"""
        # 计算RSV
        low_min = low.rolling(window=n).min()
        high_max = high.rolling(window=n).max()
        
        rsv = (close - low_min) / (high_max - low_min) * 100
        rsv = rsv.fillna(50)
        
        # 计算K值
        k = pd.Series(50.0, index=rsv.index)
        for i in range(len(rsv)):
            if i == 0:
                k[i] = 50.0
            else:
                k[i] = (2/3) * k[i-1] + (1/3) * rsv[i]
        
        # 计算D值
        d = pd.Series(50.0, index=k.index)
        for i in range(len(k)):
            if i == 0:
                d[i] = 50.0
            else:
                d[i] = (2/3) * d[i-1] + (1/3) * k[i]
        
        # 计算J值
        j = 3 * k - 2 * d
        
        return {
            'k': k.values,
            'd': d.values,
            'j': j.values
        }
    
    def _check_moving_average_trend(self, stock_hist: pd.DataFrame) -> Dict[str, bool]:
        """检查均线趋势"""
        if len(stock_hist) < 30:
            return {'ma5_up': False, 'ma10_up': False, 'ma20_up': False, 'price_above_ma20': False}
            
        close = stock_hist['收盘']
        
        # 计算均线
        ma5 = close.rolling(window=5).mean()
        ma10 = close.rolling(window=10).mean()
        ma20 = close.rolling(window=20).mean()
        
        # 判断均线趋势
        ma5_up = ma5.iloc[-1] > ma5.iloc[-2] > ma5.iloc[-3]
        ma10_up = ma10.iloc[-1] > ma10.iloc[-2]
        ma20_up = ma20.iloc[-1] > ma20.iloc[-2]
        price_above_ma20 = close.iloc[-1] > ma20.iloc[-1]
        
        return {
            'ma5_up': ma5_up,
            'ma10_up': ma10_up,
            'ma20_up': ma20_up,
            'price_above_ma20': price_above_ma20
        }
        
    def _check_volume_pattern(self, stock_hist: pd.DataFrame, recent_dates: List[str]) -> Dict[str, bool]:
        """检查成交量模式"""
        if len(stock_hist) < 5 or len(recent_dates) < 5:
            return {'shrinking_volume': False, 'end_of_day_rise': False}
            
        # 将日期标准化
        stock_hist['日期标准'] = stock_hist['日期'].astype(str).str.replace("-", "")
        
        # 获取最近几天的交易量
        volumes = []
        for date in recent_dates[:3]:  # 只看最近3天
            if date in stock_hist['日期标准'].values:
                vol = float(stock_hist[stock_hist['日期标准'] == date]['成交量'].values[0])
                volumes.append(vol)
                
        # 判断是否缩量回调(回调日成交量小于涨停日)
        shrinking_volume = False
        if len(volumes) >= 2 and volumes[0] < volumes[1]:
            shrinking_volume = True
            
        # 判断最近交易日尾盘是否上涨(收盘价高于开盘价)
        end_of_day_rise = False
        latest_date = recent_dates[0]
        if latest_date in stock_hist['日期标准'].values:
            latest_open = float(stock_hist[stock_hist['日期标准'] == latest_date]['开盘'].values[0])
            latest_close = float(stock_hist[stock_hist['日期标准'] == latest_date]['收盘'].values[0])
            end_of_day_rise = latest_close > latest_open
            
        return {
            'shrinking_volume': shrinking_volume,
            'end_of_day_rise': end_of_day_rise
        }
        
    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10, filter_stocks: bool = True) -> List[Stock]:        
        try:
            # 获取相关交易日期
            recent_dates = self._get_trade_dates(buy_date, days_needed=30)  # 增加获取的交易日数量用于计算更多指标
            if not recent_dates:
                return []
                
            date_4days_ago = recent_dates[4]  # 涨停日
            date_3days_ago = recent_dates[3]  # 上涨日
            date_2days_ago = recent_dates[2]  # 回调日1
            date_1day_ago = recent_dates[1]   # 回调日2
            latest_date = recent_dates[0]     # 最近交易日
            
            logger.info(f"将获取 {date_4days_ago} 的涨停股票数据...")
            
            # 获取涨停股票数据
            limit_up_stocks = ak.stock_zt_pool_em(date=date_4days_ago)
            
            if limit_up_stocks.empty:
                logger.warning(f"{date_4days_ago} 没有涨停股票数据")
                return []
            
            logger.info(f"成功获取数据，共 {len(limit_up_stocks)} 条记录")
            
            # 筛选沪深股票(放宽条件，包括创业板和科创板)
            if filter_stocks:
                valid_stocks = limit_up_stocks[
                    (limit_up_stocks['代码'].str.startswith('00') | 
                     limit_up_stocks['代码'].str.startswith('60') |
                     limit_up_stocks['代码'].str.startswith('30') |  # 创业板
                     limit_up_stocks['代码'].str.startswith('68'))    # 科创板
                ]
                
                # 排除ST股票
                filtered_stocks = valid_stocks[~valid_stocks['名称'].str.contains('ST')]
                logger.info(f"筛选后股票数: {len(filtered_stocks)}")
            else:
                filtered_stocks = limit_up_stocks
            
            # 存储符合条件的股票
            stocks = []
            
            # 使用tqdm显示进度
            for idx, stock_info in tqdm(filtered_stocks.iterrows(), total=len(filtered_stocks), desc="处理股票"):
                stock_code = stock_info['代码']
                stock_name = stock_info['名称']
                
                try:
                    # 获取股票历史数据 - 扩大日期范围以计算指标
                    start_date = (datetime.datetime.strptime(date_4days_ago, "%Y%m%d") - 
                                 datetime.timedelta(days=60)).strftime("%Y%m%d")  # 获取更长的历史数据
                    
                    stock_hist = ak.stock_zh_a_hist(symbol=stock_code, period="daily", 
                                                   start_date=start_date, end_date=latest_date, 
                                                   adjust="qfq")
                    
                    # 检查数据是否完整
                    if len(stock_hist) < 5:  # 需要5个交易日的数据
                        continue
                    
                    # 将日期列转换为标准格式以便于比较
                    stock_hist['日期标准'] = stock_hist['日期'].astype(str).str.replace("-", "")
                    
                    # 检查需要的日期是否都在数据中
                    required_dates = [date_4days_ago, date_3days_ago, date_2days_ago, date_1day_ago, latest_date]
                    if not all(date in stock_hist['日期标准'].values for date in required_dates):
                        continue
                    
                    # 提取所需数据
                    volume_4days_ago = float(stock_hist[stock_hist['日期标准'] == date_4days_ago]['成交量'].values[0])
                    volume_3days_ago = float(stock_hist[stock_hist['日期标准'] == date_3days_ago]['成交量'].values[0])
                    
                    pct_chg_3days_ago = float(stock_hist[stock_hist['日期标准'] == date_3days_ago]['涨跌幅'].values[0])
                    pct_chg_2days_ago = float(stock_hist[stock_hist['日期标准'] == date_2days_ago]['涨跌幅'].values[0])
                    pct_chg_1day_ago = float(stock_hist[stock_hist['日期标准'] == date_1day_ago]['涨跌幅'].values[0])
                    
                    high_4days_ago = float(stock_hist[stock_hist['日期标准'] == date_4days_ago]['最高'].values[0])
                    low_4days_ago = float(stock_hist[stock_hist['日期标准'] == date_4days_ago]['最低'].values[0])
                    
                    # 计算特定价格点：4日前最低价+(最高价-最低价)*0.25 (放宽条件)
                    price_point = low_4days_ago + (high_4days_ago - low_4days_ago) * self.config['price_point_factor']
                    
                    low_3days_ago = float(stock_hist[stock_hist['日期标准'] == date_3days_ago]['最低'].values[0])
                    latest_close = float(stock_hist[stock_hist['日期标准'] == latest_date]['收盘'].values[0])
                    
                    # 计算技术指标
                    indicators = self._calculate_technical_indicators(stock_hist)
                    ma_trends = self._check_moving_average_trend(stock_hist)
                    volume_patterns = self._check_volume_pattern(stock_hist, recent_dates)
                    
                    # 计算回调幅度
                    high_3days_ago = float(stock_hist[stock_hist['日期标准'] == date_3days_ago]['最高'].values[0])
                    avg_downtrend_pct = (pct_chg_2days_ago + pct_chg_1day_ago) / 2
                    
                    # 检查成交量放大倍数
                    volume_ratio = volume_3days_ago / volume_4days_ago
                    
                    # 修改条件判断，放宽部分要求
                    base_conditions = (
                        pct_chg_3days_ago > 0 and  # 3日前涨
                        avg_downtrend_pct < 0 and  # 近两日平均回调为负
                        volume_ratio >= self.config['volume_ratio_threshold'] and  # 成交量放大(放宽到1.3倍)
                        abs(pct_chg_2days_ago + pct_chg_1day_ago) < self.config['max_pullback']  # 放宽最大回调幅度到12%
                    )
                    
                    # 增加新的条件组合，允许价格点条件不满足但其他技术指标优异的情况
                    technical_conditions = (
                        indicators['rsi'] < 40 or  # RSI低于40(超卖)
                        (indicators['k'] < 30 and indicators['j'] < 30) or  # KDJ双低
                        (ma_trends['ma5_up'] and latest_close > stock_hist['收盘'].mean()) or  # 5日均线上涨且价格高于平均
                        volume_patterns['end_of_day_rise']  # 尾盘上涨
                    )
                    
                    # 主条件组合：基础条件满足 且 (价格点条件满足 或 技术条件满足)
                    if base_conditions and (low_3days_ago > price_point or technical_conditions):
                        # 计算成交量变化率
                        volume_change_ratio = (volume_ratio - 1) * 100
                        
                        # 计算价格条件满足的程度
                        price_condition_ratio = ((low_3days_ago - price_point) / low_4days_ago) * 100 if low_3days_ago > price_point else 0
                        
                        # 创建Stock对象并添加到结果列表
                        stock = Stock()
                        stock.code = stock_code
                        stock.name = stock_name
                        stock.current_price = float(latest_close)
                        stock.buy_price = float(latest_close)
                        
                        # 设置动态卖出价：根据技术指标调整目标收益率(4-10%)
                        target_percent = 0.07  # 默认7%
                        if indicators['rsi'] < 30:
                            target_percent = 0.1  # RSI极低时，目标收益提高到10%
                        elif indicators.get('boll_position', 0.5) < 0.2:
                            target_percent = 0.09  # 布林带底部，目标收益9%
                        
                        # 确保卖出价至少比买入价高出目标百分比
                        min_target_price = round(stock.buy_price * (1 + target_percent), 2)
                        
                        # 涨停日高点的95%作为上限目标，但确保不低于最小目标价
                        high_point_target = round(high_4days_ago * 0.95, 2)
                        
                        # 如果涨停日高点的95%超过了买入价的15%，则卖出价最高不超过买入价的15%
                        max_target_price = round(stock.buy_price * 1.15, 2)
                        if high_point_target > min_target_price:
                            stock.sell_price = min(high_point_target, max_target_price)
                        else:
                            stock.sell_price = min_target_price
                        
                        # 动态设置止损价，超卖程度深时可以放宽止损点
                        stop_loss_percent = 0.03  # 默认3%
                        if indicators['rsi'] < 30 or indicators.get('boll_position', 0.5) < 0.1:
                            stop_loss_percent = 0.04  # 超卖严重时，止损放宽到4%
                            
                        stock.stop_loss = round(stock.buy_price * (1 - stop_loss_percent), 2)
                        
                        # 计算综合得分
                        stock.score = self._calculate_score(
                            volume_change_ratio, 
                            price_condition_ratio, 
                            indicators['rsi'], 
                            avg_downtrend_pct,
                            indicators.get('macd', 0),
                            indicators.get('boll_position', 0.5)
                        )
                        
                        # 生成详细建议原因
                        tech_signals = []
                        if indicators['rsi'] < 40:
                            tech_signals.append(f"RSI:{indicators['rsi']:.1f}(超卖)")
                        if indicators.get('k', 50) < 30:
                            tech_signals.append(f"KDJ:{indicators.get('k', 50):.1f}/{indicators.get('d', 50):.1f}/{indicators.get('j', 50):.1f}")
                        if indicators.get('boll_position', 0.5) < 0.3:
                            tech_signals.append("布林带底部")
                        if ma_trends['ma5_up']:
                            tech_signals.append("均线企稳")
                        if volume_patterns['end_of_day_rise']:
                            tech_signals.append("尾盘走强")
                            
                        tech_signal_str = "，".join(tech_signals) if tech_signals else "无特殊信号"
                        
                        stock.suggest_reason = (
                            f"涨停回调买入。{date_4days_ago}涨停，{date_3days_ago}上涨(+{pct_chg_3days_ago:.2f}%)，"
                            f"成交量增加{volume_change_ratio:.2f}%(达{volume_ratio:.2f}倍)，近两日回调{avg_downtrend_pct:.2f}%。"
                            f"技术信号：{tech_signal_str}。目标价:{stock.sell_price}，止损价:{stock.stop_loss}"
                        )
                        stocks.append(stock)
                                                
                except Exception as e:
                    logger.warning(f"处理股票 {stock_code} 时出错: {str(e)}")
                    continue
            
            # 根据得分排序
            stocks.sort(key=lambda x: x.score, reverse=True)
            if len(stocks) > limit_stock_count:
                stocks = stocks[:limit_stock_count]
                
            logger.info(f"共找到 {len(stocks)} 只符合条件的股票")
            return stocks
                
        except Exception as e:
            logger.error(f"程序执行出错: {str(e)}", exc_info=True)
            return []
