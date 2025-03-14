from strategy.base import Strategy, Stock
from typing import List, Dict, Tuple, Optional
import akshare as ak
import datetime
import pandas as pd
import numpy as np
import sys
import requests
import logging
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LowStockStrategy(Strategy):
    def __init__(self):
        super().__init__(name="low_stock")
        # 配置HTTP会话，增加重试机制
        self.session = requests.Session()
        retries = requests.adapters.Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.session.mount('http://', requests.adapters.HTTPAdapter(max_retries=retries))
        self.session.mount('https://', requests.adapters.HTTPAdapter(max_retries=retries))
        
        # 行业平均水平的折扣率 (例如：要求低于行业均值的百分比)
        self.config = {
            'industry_pe_discount': 20,     # PE要求比行业平均低20%
            'industry_pb_discount': 20,     # PB要求比行业平均低20%
            'industry_roe_premium': 10,     # ROE要求比行业平均高10%
            'min_dividend_yield': 2,        # 最小股息率(%)
            'max_debt_ratio': 60,           # 最大负债率(%)
            'min_current_ratio': 1.5,       # 最小流动比率
            'min_market_cap': 50,           # 最小市值(亿元)
            'max_price_change': 30,         # 最大股价变动(过去一年内, %)
            
            # 绝对阈值作为保障措施
            'absolute_max_pe': 30,          # 绝对最大PE
            'absolute_max_pb': 3,           # 绝对最大PB
            'absolute_min_roe': 5,          # 绝对最小ROE
        }
    
    
    def _calculate_score(self, data: Dict) -> float:
        """计算股票估值得分，与行业比较"""
        # 基础分数，满分100
        score = 0
        
        # 市盈率评分 (0-25分) - 与行业对比
        if data['industry_pe_avg'] and data['pe'] > 0 and data['pe'] < 100:
            # 计算PE相对于行业的折扣率
            pe_discount = (data['industry_pe_avg'] - data['pe']) / data['industry_pe_avg'] * 100
            if pe_discount >= self.config['industry_pe_discount']:
                pe_score = 25  # 达到或超过目标折扣率
            else:
                # 按比例计分
                pe_ratio = pe_discount / self.config['industry_pe_discount']
                pe_score = max(0, 25 * pe_ratio)
        elif data['pe'] <= 0 or data['pe'] >= 100:
            pe_score = 0  # 负PE或高PE不加分
        elif data['pe'] <= 10:
            pe_score = 20  # 绝对低PE仍然得分，但低于与行业比较的情况
        else:
            pe_score = max(0, 20 * (1 - (data['pe'] - 10) / (self.config['absolute_max_pe'] - 10)))
        
        # 市净率评分 (0-20分) - 与行业对比
        if data['industry_pb_avg'] and data['pb'] > 0 and data['pb'] < 20:
            # 计算PB相对于行业的折扣率
            pb_discount = (data['industry_pb_avg'] - data['pb']) / data['industry_pb_avg'] * 100
            if pb_discount >= self.config['industry_pb_discount']:
                pb_score = 20  # 达到或超过目标折扣率
            else:
                # 按比例计分
                pb_ratio = pb_discount / self.config['industry_pb_discount']
                pb_score = max(0, 20 * pb_ratio)
        elif data['pb'] <= 0:
            pb_score = 0  # 负PB不加分
        elif data['pb'] <= 1:
            pb_score = 15  # 绝对低PB仍然得分，但低于与行业比较的情况
        else:
            pb_score = max(0, 15 * (1 - (data['pb'] - 1) / (self.config['absolute_max_pb'] - 1)))
        
        # ROE评分 (0-15分) - 与行业对比
        if data['industry_roe_avg'] and data['roe'] > 0:
            # 计算ROE相对于行业的溢价率
            roe_premium = (data['roe'] - data['industry_roe_avg']) / data['industry_roe_avg'] * 100
            if roe_premium >= self.config['industry_roe_premium']:
                roe_score = 15  # 达到或超过目标溢价率
            else:
                # 按比例计分
                roe_ratio = roe_premium / self.config['industry_roe_premium']
                roe_score = max(0, 15 * (0.5 + roe_ratio / 2))  # 基础分7.5分，上下浮动
        elif data['roe'] <= 0:
            roe_score = 0  # 负ROE不加分
        else:
            roe_score = min(12, data['roe'] / 2)  # 绝对ROE得分，但上限低于与行业比较
        
        # 股息率评分 (0-15分)
        dividend_score = min(15, data['dividend_yield'] * 3)
        
        # 负债率评分 (0-10分)
        debt_score = max(0, 10 * (1 - data['debt_ratio'] / 100)) if data['debt_ratio'] <= 100 else 0
        
        # 流动比率评分 (0-10分)
        current_score = min(10, data['current_ratio'] * 5) if data['current_ratio'] > 0 else 0
        
        # 营收增长评分 (0-5分)
        growth_score = min(5, max(0, data['revenue_growth'] / 5))
        
        # 总分
        score = pe_score + pb_score + roe_score + dividend_score + debt_score + current_score + growth_score
        
        return round(score, 2)
    
    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10, filter_stocks: bool = True) -> List[Stock]:
        try:
            logger.info("获取A股所有股票列表...")
            stock_list = ak.stock_zh_a_spot_em()
            
            if filter_stocks:
                # 筛选沪深股票，排除ST股票
                stock_list = stock_list[
                    (stock_list['代码'].str.startswith('00') | 
                     stock_list['代码'].str.startswith('60')) &
                    (~stock_list['名称'].str.contains('ST'))
                ]
            
            logger.info(f"开始筛选低估值股票，共 {len(stock_list)} 只股票待分析")
            
            # 获取行业数据

            yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y%m%d')
            industry_data = ak.stock_industry_pe_ratio_cninfo(date=yesterday)

            # 存储符合条件的股票
            stocks = []
            
            for idx, row in stock_list.iterrows():
                stock_code = row['代码']
                stock_name = row['名称']
                current_price = float(row['最新价'])


                stock_info = ak.stock_individual_info_em(symbol=stock_code)
                industry = stock_info[stock_info['item'] == '行业']['value'].iloc[0]

                # 获取行业数据
                current_industry_data = industry_data[industry_data['行业名称'] == industry]
                if current_industry_data.empty:
                    print(f"行业 {industry} 没有数据")
                    continue
            
                industry_pe_avg = current_industry_data.iloc[0]['静态市盈率-加权平均']
                industry_pe_avg2 = current_industry_data.iloc[0]['静态市盈率-中位数']
                
                print(industry_pe_avg, industry_pe_avg2)


                stock_spot = ak.stock_individual_spot_xq(symbol=('SZ' + stock_code if stock_code.startswith('00') else 'SH' + stock_code))
                ttm_pe = stock_spot[stock_spot['item'] == '市盈率(动)'].iloc[0]['value']
                lyr_pe = stock_spot[stock_spot['item'] == '市盈率(静)'].iloc[0]['value']

                if ttm_pe <= 0 or lyr_pe <= 0:
                    continue

                if ttm_pe > industry_pe_avg  or lyr_pe > industry_pe_avg:
                    continue

                stock = Stock()
                stock.code = stock_code
                stock.name = stock_name
                stock.current_price = current_price
                stock.buy_price = current_price
                stock.sell_price = round(current_price * 1.1, 2)
                stock.score = 100

                stocks.append(stock)
                    
            
            # 根据得分排序
            stocks.sort(key=lambda x: x.score, reverse=True)
            if len(stocks) > limit_stock_count:
                stocks = stocks[:limit_stock_count]
            
            logger.info(f"共找到 {len(stocks)} 只符合条件的低估值股票")
            return stocks
            
        except Exception as e:
            logger.error(f"程序执行出错: {str(e)}", exc_info=True)
            return []
