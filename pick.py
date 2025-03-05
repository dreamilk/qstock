import akshare as ak
import datetime
import pandas as pd
import time
import sys

# 设置请求超时
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置请求会话，添加重试和超时机制
session = requests.Session()
retry = Retry(total=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

# 替换akshare的默认会话
try:
    ak.cons.session = session
except:
    pass  # 如果无法直接替换会话，则忽略

def print_with_flush(message):
    """打印消息并立即刷新输出"""
    print(message)
    sys.stdout.flush()

# 主程序
def main():
    print_with_flush("开始获取交易日期...")
    try:
        # 获取最近一段时间的交易日历
        trade_date_df = ak.tool_trade_date_hist_sina()
        trade_dates = [str(date).replace("-", "") for date in trade_date_df["trade_date"].tolist()]
        trade_dates = sorted(trade_dates, reverse=True)
        
        today = datetime.datetime.now().strftime('%Y%m%d')
        # 找出最近日期之前的交易日
        recent_dates = [date for date in trade_dates if date <= today]
        
        if len(recent_dates) <= 4:
            print_with_flush("无法获取足够的交易日数据")
            return
            
        # 获取相关交易日期
        date_4days_ago = recent_dates[4]  # 4个交易日前（涨停日）
        date_3days_ago = recent_dates[3]  # 3个交易日前（需为上涨，成交量需大于涨停日）
        date_2days_ago = recent_dates[2]  # 2个交易日前（需为下跌）
        date_1day_ago = recent_dates[1]   # 1个交易日前（需为下跌）
        latest_date = recent_dates[0]     # 最近交易日
        
        print_with_flush(f"将获取 {date_4days_ago} 的涨停股票数据...")
        
        # 获取涨停股票数据
        print_with_flush("正在请求数据，请稍候...")
        limit_up_stocks = ak.stock_zt_pool_em(date=date_4days_ago)
        
        print_with_flush(f"成功获取数据，共 {len(limit_up_stocks)} 条记录")
        
        if limit_up_stocks.empty:
            print_with_flush(f"{date_4days_ago} 没有涨停股票数据")
            return
        
        # 筛选沪深主板股票 (00和60开头)，明确排除创业板(30开头)和科创板(68开头)
        print_with_flush("筛选沪深主板股票，排除科创板和创业板...")
        main_board_stocks = limit_up_stocks[
            (limit_up_stocks['代码'].str.startswith('00') | 
             limit_up_stocks['代码'].str.startswith('60'))
        ]
        
        # 排除ST股票
        print_with_flush("排除ST股票...")
        filtered_stocks = main_board_stocks[~main_board_stocks['名称'].str.contains('ST')]
        print_with_flush(f"筛选后股票数: {len(filtered_stocks)}")
        
        # 继续筛选：3个交易日前为涨，近两个交易日为跌，3日前成交量大于4日前成交量
        print_with_flush("开始筛选符合涨跌和成交量条件的股票...")
        result_stocks = []
        
        for idx, stock in filtered_stocks.iterrows():
            stock_code = stock['代码']
            stock_name = stock['名称']
            
            try:
                # 获取股票历史数据
                stock_hist = ak.stock_zh_a_hist(symbol=stock_code, period="daily", 
                                               start_date=date_4days_ago, end_date=latest_date, 
                                               adjust="qfq")
                
                # 检查数据是否完整
                if len(stock_hist) < 5:  # 需要5个交易日的数据
                    print_with_flush(f"股票 {stock_code} 数据不完整，跳过")
                    continue
                
                # 检查日期是否匹配
                dates_in_hist = [d.replace("-", "") for d in stock_hist['日期'].astype(str)]
                
                if (date_4days_ago in dates_in_hist and
                    date_3days_ago in dates_in_hist and 
                    date_2days_ago in dates_in_hist and 
                    date_1day_ago in dates_in_hist):
                    
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
                    price_point = low_4days_ago + (high_4days_ago - low_4days_ago) * 0.3
                    
                    # 获取3日前的最低价
                    low_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['最低'].values[0]
                    
                    # 检查所有条件：
                    # 1. 3日前涨，近两日跌
                    # 2. 3日前成交量大于4日前
                    # 3. 3日前最低价高于特定价格点
                    if (pct_chg_3days_ago > 0 and 
                        pct_chg_2days_ago < 0 and 
                        pct_chg_1day_ago < 0 and
                        volume_3days_ago > volume_4days_ago and
                        low_3days_ago > price_point):
                        
                        # 计算成交量变化率
                        volume_change_ratio = (volume_3days_ago / volume_4days_ago - 1) * 100
                        
                        # 计算价格条件满足的程度
                        price_condition_ratio = ((low_3days_ago - price_point) / low_4days_ago) * 100
                        
                        result_stocks.append({
                            '代码': stock_code,
                            '名称': stock_name,
                            '涨停日': date_4days_ago,
                            '3日前涨幅': f"{pct_chg_3days_ago:.2f}%",
                            '2日前涨幅': f"{pct_chg_2days_ago:.2f}%",
                            '1日前涨幅': f"{pct_chg_1day_ago:.2f}%",
                            '成交量变化率': f"{volume_change_ratio:.2f}%",
                            '价格条件超额': f"{price_condition_ratio:.2f}%"
                        })
                        print_with_flush(f"股票 {stock_code} {stock_name} 符合条件，成交量增加 {volume_change_ratio:.2f}%，价格条件超额 {price_condition_ratio:.2f}%")
            
            except Exception as e:
                print_with_flush(f"处理股票 {stock_code} 时出错: {e}")
                continue
        
        # 转换为DataFrame
        if result_stocks:
            result_df = pd.DataFrame(result_stocks)
            
            # 显示结果
            print_with_flush(f"\n符合所有筛选条件的股票列表（共 {len(result_df)} 只）：")
            print(result_df)
            
            # 保存结果
            output_file = f'filtered_stocks_{date_4days_ago}.csv'
            result_df.to_csv(output_file, encoding='utf-8-sig', index=False)
            print_with_flush(f"\n数据已保存到 {output_file}")
        else:
            print_with_flush("没有找到符合所有筛选条件的股票")
        
    except Exception as e:
        print_with_flush(f"程序执行出错: {e}")

if __name__ == "__main__":
    main()
