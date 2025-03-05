import akshare as ak
import datetime
import pandas as pd
import time
import sys
import argparse  # Add argparse for command-line arguments
import matplotlib.pyplot as plt
import mplfinance as mpf
from matplotlib.ticker import AutoMinorLocator
import os

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

def generate_kline_chart(stock_code, stock_name,reference_date, output_dir="charts"):
    """生成K线图并保存
    
    Args:
        stock_code: 股票代码
        reference_date: 参考日期 (YYYYMMDD格式)
        output_dir: 输出目录
    """
    try:
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 计算要显示的日期范围
        reference_date_dt = datetime.datetime.strptime(reference_date, '%Y%m%d')
        start_date = reference_date_dt - datetime.timedelta(days=60)  # 多取几天以确保有足够的交易日
        end_date_plus3 = reference_date_dt + datetime.timedelta(days=10)  # 多取几天以确保有后续交易日
        
        today = datetime.datetime.now()
        end_date = min(end_date_plus3, today)
        
        # 直接获取股票数据
        start_date_str = start_date.strftime('%Y%m%d')
        end_date_str = end_date.strftime('%Y%m%d')
        
        print_with_flush(f"获取 {stock_code} 从 {start_date_str} 至 {end_date_str} 的数据...")
        
        # 使用akshare获取数据
        hist_data = ak.stock_zh_a_hist(
            symbol=stock_code, 
            period="daily", 
            start_date=start_date_str, 
            end_date=end_date_str, 
            adjust="qfq"
        )
        
        # 检查数据量是否足够
        if len(hist_data) < 5:
            print_with_flush(f"股票 {stock_code} 的K线图数据不足，跳过绘图")
            return None
            
        # 确保有数据
        if hist_data.empty:
            print_with_flush(f"股票 {stock_code} 在指定时间范围内没有数据，跳过绘图")
            return None
        
        # 转换日期为datetime格式
        hist_data['日期'] = pd.to_datetime(hist_data['日期'])
        hist_data.set_index('日期', inplace=True)
        
        # 重命名列以符合mplfinance要求
        hist_data_renamed = hist_data.rename(columns={
            '开盘': 'Open',
            '收盘': 'Close',
            '最高': 'High',
            '最低': 'Low',
            '成交量': 'Volume'
        })
        
        # 截取日期范围内的数据 - 确保使用近期数据
        plot_start_date = reference_date_dt - datetime.timedelta(days=30)
        plot_data = hist_data_renamed[(hist_data_renamed.index >= plot_start_date) & 
                                     (hist_data_renamed.index <= end_date)].copy()
        
        # 计算移动平均线 - 使用.loc来避免SettingWithCopyWarning
        plot_data.loc[:, 'MA10'] = plot_data['Close'].rolling(window=10).mean()
        plot_data.loc[:, 'MA20'] = plot_data['Close'].rolling(window=20).mean()
        
        # 设置K线图样式
        mc = mpf.make_marketcolors(up='red', down='green', inherit=True)
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--')
        
        # 添加均线 - 只有当有足够的数据点时
        add_plots = []
        if not plot_data['MA10'].isnull().all():
            add_plots.append(mpf.make_addplot(plot_data['MA10'], color='blue', width=1))
        if not plot_data['MA20'].isnull().all():
            add_plots.append(mpf.make_addplot(plot_data['MA20'], color='purple', width=1))
        
        # 计算文件名 - 保持要求的格式但确保文件名安全
        end_date_str = end_date.strftime('%Y%m%d')
        # 替换股票名称中可能导致文件名问题的字符
        safe_stock_name = ''.join(c if c.isalnum() else '_' for c in stock_name)
        filename = f"{end_date_str}_{stock_code}_{safe_stock_name}.png"
        filepath = os.path.join(output_dir, filename)
        
        # 绘制K线图 - 使用constrained_layout替代tight_layout
        kwargs = {
            'type': 'candle',
            'style': s,
            'addplot': add_plots if add_plots else None,
            'volume': True,
            'figsize': (12, 8),
            'title': f"{stock_code}",
            'datetime_format': '%Y-%m-%d',  # 设置日期格式
            'xrotation': 45,  # 旋转x轴日期标签以便更好地显示
            'returnfig': True,
            'figratio': (12, 8)
        }
        
        fig, axes = mpf.plot(plot_data, **kwargs)
        
        # 设置x轴的日期显示
        axes[0].xaxis.set_major_locator(plt.MaxNLocator(10))  # 限制最多显示10个日期标签
        
        # 不再使用tight_layout，而是调整图表间距
        fig.subplots_adjust(hspace=0, bottom=0.15)
        
        # 保存图表
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        print_with_flush(f"已保存K线图: {filepath}")
        return filepath
    except Exception as e:
        print_with_flush(f"生成股票 {stock_code} K线图时出错: {e}")
        return None

# 主程序
def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='股票筛选工具')
    parser.add_argument('-d', '--date', help='指定日期 (格式: YYYYMMDD)', default=None)
    args = parser.parse_args()
    
    # 设置日期
    if args.date:
        today = args.date
        print_with_flush(f"使用指定日期: {today}")
    else:
        today = datetime.datetime.now().strftime('%Y%m%d')
        print_with_flush(f"使用今日日期: {today}")
    
    print_with_flush("开始获取交易日期...")
    try:
        # 获取最近一段时间的交易日历
        trade_date_df = ak.tool_trade_date_hist_sina()
        trade_dates = [str(date).replace("-", "") for date in trade_date_df["trade_date"].tolist()]
        trade_dates = sorted(trade_dates, reverse=True)
        
        # 找出指定日期之前的交易日
        recent_dates = [date for date in trade_dates if date <= today]
        
        if len(recent_dates) <= 5:  # Changed from 4 to 5 to accommodate 5 days ago
            print_with_flush("无法获取足够的交易日数据")
            return
            
        # 获取相关交易日期
        date_5days_ago = recent_dates[5]  # 5个交易日前（需为上涨）
        date_4days_ago = recent_dates[4]  # 4个交易日前（涨停日）
        date_3days_ago = recent_dates[3]  # 3个交易日前（最高价需超过4日前最高价，不要求涨）
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
                                               start_date=(datetime.datetime.strptime(date_4days_ago, '%Y%m%d') - datetime.timedelta(days=60)).strftime('%Y%m%d'), 
                                               end_date=latest_date, 
                                               adjust="qfq")
                
                # 检查数据是否完整
                if len(stock_hist) < 5:  # 需要5个交易日的数据
                    print_with_flush(f"股票 {stock_code} 数据不完整，跳过")
                    continue
                
                # 检查日期是否匹配
                dates_in_hist = [d.replace("-", "") for d in stock_hist['日期'].astype(str)]
                
                if (date_5days_ago in dates_in_hist and
                    date_4days_ago in dates_in_hist and
                    date_3days_ago in dates_in_hist and 
                    date_2days_ago in dates_in_hist and 
                    date_1day_ago in dates_in_hist):
                    
                    # 获取5日前的涨跌幅
                    pct_chg_5days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_5days_ago]['涨跌幅'].values[0]
                    
                    # 获取各日期的涨跌幅
                    pct_chg_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['涨跌幅'].values[0]
                    pct_chg_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['涨跌幅'].values[0]
                    pct_chg_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['涨跌幅'].values[0]
                    
                    # 获取涨停日和次日的成交量
                    volume_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['成交量'].values[0]
                    volume_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['成交量'].values[0]
                    
                    # 获取4日前(涨停日)的最高价和最低价
                    high_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['最高'].values[0]
                    low_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['最低'].values[0]
                    close_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['收盘'].values[0]
                    open_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['开盘'].values[0]
                    
                    # 获取3日前的最低价和最高价
                    low_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['最低'].values[0]
                    high_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['最高'].values[0]
                    
                    # 获取2日前和1日前的开盘价和收盘价
                    open_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['开盘'].values[0]
                    close_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['收盘'].values[0]
                    open_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['开盘'].values[0]
                    close_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['收盘'].values[0]
                    
                    # 获取2日前和1日前的最高价和最低价
                    high_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['最高'].values[0]
                    low_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['最低'].values[0]
                    high_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['最高'].values[0]
                    low_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['最低'].values[0]
                    
                    # 计算2日前和1日前的开盘与收盘差值
                    drop_2days_ago = open_2days_ago - close_2days_ago
                    drop_1day_ago = open_1day_ago - close_1day_ago
                    
                    # 计算2日前和1日前的价格区间（最高价-最低价）
                    range_2days_ago = high_2days_ago - low_2days_ago
                    range_1day_ago = high_1day_ago - low_1day_ago
                    
                    # 获取前一天收盘价和最低价
                    prev_day_close = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['收盘'].values[0]
                    prev_day_low = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['最低'].values[0]
                    
                    # 计算10日均线和20日均线
                    stock_hist['MA10'] = stock_hist['收盘'].rolling(window=10).mean()
                    stock_hist['MA20'] = stock_hist['收盘'].rolling(window=20).mean()
                    
                    # 获取最近交易日的均线值
                    latest_ma10 = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['MA10'].values[0]
                    latest_ma20 = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['MA20'].values[0]
                    
                    # 计算成交量变化率
                    volume_change_ratio = (volume_3days_ago / volume_4days_ago - 1) * 100
                    
                    # 获取今日实时数据
                    try:
                        today_data = ak.stock_zh_a_spot_em()
                        today_stock_data = today_data[today_data['代码'] == stock_code]
                        
                        if not today_stock_data.empty:
                            today_current = today_stock_data['最新价'].values[0]
                            today_high = today_stock_data['最高'].values[0]
                            today_low = today_stock_data['最低'].values[0]
                        else:
                            today_current = today_high = today_low = float('nan')
                    except Exception as e:
                        print_with_flush(f"获取 {stock_code} 今日数据时出错: {e}")
                        today_current = today_high = today_low = float('nan')
                    
                    # 检查所有条件：
                    # 1. 5日前涨，近两日跌
                    # 2. 3日前最高价高于4日前开盘价+(收盘价-开盘价)*0.6
                    # 3. 3日前成交量大于4日前
                    # 4. 3日前最低价高于4日前最低价+(最高价-最低价)*0.05
                    # 5. 前一天收盘价小于前四天开盘价+(收盘价-开盘价)*0.5
                    # 6. 2日前收盘差值 大于 1日前的收盘茶汁*0.7
                    if (pct_chg_5days_ago > -0.02 and 
                        pct_chg_2days_ago < 0.05 and 
                        pct_chg_1day_ago < 0.05 and
                        high_3days_ago > (open_4days_ago + (close_4days_ago - open_4days_ago) * 0.6) and
                        volume_3days_ago > volume_4days_ago and
                        low_3days_ago > low_4days_ago + (high_4days_ago - low_4days_ago) * 0.05 and
                        prev_day_close < (open_4days_ago + (close_4days_ago - open_4days_ago) * 0.5) and
                        drop_2days_ago > drop_1day_ago*0.7):
                        
                        # 生成K线图
                        print_with_flush(f"正在生成 {stock_code} {stock_name} 的K线图...")
                        chart_path = generate_kline_chart(stock_code, stock_name, today)
                        
                        result_stocks.append({
                            '代码': stock_code,
                            '名称': stock_name,
                            '涨停日': date_4days_ago,
                            '5日前涨幅': f"{pct_chg_5days_ago:.2f}%",
                            '3日前涨幅': f"{pct_chg_3days_ago:.2f}%",
                            '2日前涨幅': f"{pct_chg_2days_ago:.2f}%",
                            '1日前涨幅': f"{pct_chg_1day_ago:.2f}%",
                            '成交量变化率': f"{volume_change_ratio:.2f}%",
                            '2日前价格跌幅': f"{drop_2days_ago:.2f}",
                            '1日前价格跌幅': f"{drop_1day_ago:.2f}",
                            '2日前价格区间': f"{range_2days_ago:.2f}",
                            '1日前价格区间': f"{range_1day_ago:.2f}",
                            '前一日收盘价': f"{prev_day_close:.2f}",
                            '前一日最低价': f"{prev_day_low:.2f}",
                            '10日均线': f"{latest_ma10:.2f}",
                            '20日均线': f"{latest_ma20:.2f}",
                            '今日最高价': f"{today_high:.2f}" if not pd.isna(today_high) else "暂无数据",
                            '今日最低价': f"{today_low:.2f}" if not pd.isna(today_low) else "暂无数据",
                            '当前价格': f"{today_current:.2f}" if not pd.isna(today_current) else "暂无数据",
                            'K线图': chart_path if chart_path else "生成失败"
                        })
                        print_with_flush(f"股票 {stock_code} {stock_name} 符合条件")
            
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
            output_file = f'pick_stocks_{today}.csv'
            result_df.to_csv(output_file, encoding='utf-8-sig', index=False)
            print_with_flush(f"\n数据已保存到 {output_file}")
        else:
            print_with_flush("没有找到符合所有筛选条件的股票")
        
    except Exception as e:
        print_with_flush(f"程序执行出错: {e}")

if __name__ == "__main__":
    main()
