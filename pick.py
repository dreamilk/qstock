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

# 显示当前运行时间
current_time = datetime.datetime.now()
print(f"运行时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')} akshare版本号: {ak.__version__}")

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
        
        # 添加买入卖出点标记的功能增强
        try:
            # 计算最近的支撑位和阻力位
            max_high = plot_data['High'].max()
            min_low = plot_data['Low'].min()
            
            # 添加支撑位和阻力位标记
            support_level = plot_data['Low'].rolling(window=5).min().iloc[-5]
            resistance_level = plot_data['High'].rolling(window=5).max().iloc[-5]
            
            # 添加支撑位和阻力位线
            add_plots.append(mpf.make_addplot([support_level] * len(plot_data), color='green', linestyle='--', width=1))
            add_plots.append(mpf.make_addplot([resistance_level] * len(plot_data), color='red', linestyle='--', width=1))
        except Exception:
            pass  # 忽略标记添加失败的情况
        
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

def calculate_entry_exit_points(stock_code, stock_hist, date_4days_ago, date_1day_ago, close_1day_ago):
    """计算推荐买入点、卖出点和预期收益
    
    Args:
        stock_code: 股票代码
        stock_hist: 股票历史数据
        date_4days_ago: 涨停日期
        date_1day_ago: 最近交易日
        close_1day_ago: 最近收盘价
    
    Returns:
        tuple: (买入价, 止损价, 目标价1, 目标价2, 最大预期收益率)
    """
    try:
        # 计算Fibonacci回调水平作为买入点参考
        high_point = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['最高'].values[0]
        
        # 确保日期比较使用相同的格式 - 全部转为字符串进行比较
        date_4days_ago_str = date_4days_ago
        date_1day_ago_str = date_1day_ago
        
        # 修复日期比较问题
        recent_low = stock_hist[(stock_hist['日期'].astype(str).str.replace("-", "") > date_4days_ago_str) & 
                               (stock_hist['日期'].astype(str).str.replace("-", "") <= date_1day_ago_str)]['最低'].min()
        
        # 计算Fib回调价位 (38.2%, 50%, 61.8%)
        price_range = high_point - recent_low
        fib_382 = high_point - price_range * 0.382
        fib_50 = high_point - price_range * 0.5
        fib_618 = high_point - price_range * 0.618
        
        # 根据当前位置确定买入点
        if close_1day_ago < fib_618:
            # 价格已经低于61.8%回调位，考虑现价附近买入
            entry_price = round(close_1day_ago * 1.02, 2)  # 略高于收盘价的买入点
        elif close_1day_ago < fib_50:
            # 价格在50%-61.8%之间，考虑在接近61.8%位置买入
            entry_price = round(max(close_1day_ago * 0.98, fib_618), 2)
        else:
            # 价格在高位，等待回调至61.8%位买入
            entry_price = round(fib_618, 2)
        
        # 设置止损点 (低于最近低点5%)
        stop_loss = round(recent_low * 0.95, 2)
        
        # 设置目标价 (Fibonacci扩展)
        target1 = round(recent_low + price_range * 1.0, 2)  # 100% 反弹
        target2 = round(recent_low + price_range * 1.618, 2)  # 161.8% 扩展
        
        # 计算预期收益率
        max_return_pct = round((target2 / entry_price - 1) * 100, 2)
        
        return entry_price, stop_loss, target1, target2, max_return_pct
    
    except Exception as e:
        print_with_flush(f"计算股票 {stock_code} 买卖点时出错: {e}")
        return None, None, None, None, None

def calculate_risk_reward_ratio(entry_price, stop_loss, target1, target2):
    """计算风险回报比
    
    Args:
        entry_price: 买入价
        stop_loss: 止损价
        target1: 目标价1
        target2: 目标价2
    
    Returns:
        float: 风险回报比
    """
    if entry_price is None or stop_loss is None or target2 is None:
        return None
    
    risk = entry_price - stop_loss
    if risk <= 0:
        return None
    
    reward = target2 - entry_price
    return round(reward / risk, 2)

def evaluate_market_strength(stock_hist, date_1day_ago):
    """评估市场强度
    
    Args:
        stock_hist: 股票历史数据
        date_1day_ago: 最近交易日
    
    Returns:
        str: 市场强度评估 ('强', '中', '弱')
    """
    try:
        # 计算RSI
        close_series = stock_hist['收盘']
        delta = close_series.diff()
        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        down = down.abs()
        
        avg_gain = up.rolling(window=14).mean()
        avg_loss = down.rolling(window=14).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # 获取最近交易日的RSI
        latest_rsi = rsi[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago].values[0]
        
        # 获取最近交易日的均线排列
        latest_ma5 = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['MA5'].values[0]
        latest_ma10 = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['MA10'].values[0]
        latest_ma20 = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['MA20'].values[0]
        
        # 评估市场强度
        if latest_rsi > 60 and latest_ma5 > latest_ma10 > latest_ma20:
            return '强'
        elif latest_rsi > 45 and latest_ma5 > latest_ma20:
            return '中'
        else:
            return '弱'
    except Exception:
        return '中'  # 默认为中等强度

# 主程序
def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='股票筛选工具')
    parser.add_argument('-d', '--date', help='指定日期 (格式: YYYYMMDD)', default=None)
    parser.add_argument('-s', '--strategy', help='选股策略 (默认: dragonhead)', default='dragonhead')
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
        
        # 继续筛选：龙回头策略的条件
        print_with_flush("开始筛选符合龙回头策略的股票...")
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
                if len(stock_hist) < 10:  # 需要至少10个交易日的数据用于计算均线
                    print_with_flush(f"股票 {stock_code} 数据不完整，跳过")
                    continue
                
                # 检查日期是否匹配
                dates_in_hist = [d.replace("-", "") for d in stock_hist['日期'].astype(str)]
                
                if (date_5days_ago in dates_in_hist and
                    date_4days_ago in dates_in_hist and
                    date_3days_ago in dates_in_hist and 
                    date_2days_ago in dates_in_hist and 
                    date_1day_ago in dates_in_hist):
                    
                    # 获取涨跌幅数据
                    pct_chg_5days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_5days_ago]['涨跌幅'].values[0]
                    pct_chg_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['涨跌幅'].values[0]
                    pct_chg_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['涨跌幅'].values[0]
                    pct_chg_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['涨跌幅'].values[0]
                    pct_chg_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['涨跌幅'].values[0]
                    
                    # 获取价格数据
                    high_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['最高'].values[0]
                    low_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['最低'].values[0]
                    close_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['收盘'].values[0]
                    open_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['开盘'].values[0]
                    
                    high_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['最高'].values[0]
                    low_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['最低'].values[0]
                    close_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['收盘'].values[0]
                    
                    high_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['最高'].values[0]
                    low_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['最低'].values[0]
                    open_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['开盘'].values[0]
                    close_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['收盘'].values[0]
                    
                    high_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['最高'].values[0]
                    low_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['最低'].values[0]
                    open_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['开盘'].values[0]
                    close_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['收盘'].values[0]
                    
                    # 获取成交量数据
                    volume_5days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_5days_ago]['成交量'].values[0]
                    volume_4days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_4days_ago]['成交量'].values[0]
                    volume_3days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_3days_ago]['成交量'].values[0]
                    volume_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['成交量'].values[0]
                    volume_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['成交量'].values[0]
                    
                    # 计算均线
                    stock_hist['MA5'] = stock_hist['收盘'].rolling(window=5).mean()
                    stock_hist['MA10'] = stock_hist['收盘'].rolling(window=10).mean()
                    stock_hist['MA20'] = stock_hist['收盘'].rolling(window=20).mean()
                    
                    # 获取最近交易日的均线值
                    latest_ma5 = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['MA5'].values[0]
                    latest_ma10 = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['MA10'].values[0]
                    latest_ma20 = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['MA20'].values[0]
                    
                    # 计算涨停日后的回调幅度（从涨停日收盘到最低点的跌幅）
                    pullback_pct = min(low_3days_ago, low_2days_ago, low_1day_ago) / close_4days_ago - 1
                    
                    # 计算均线支撑情况
                    close_to_ma10 = abs(low_1day_ago / latest_ma10 - 1) < 0.03  # 最低价接近10日线
                    close_to_ma20 = abs(low_1day_ago / latest_ma20 - 1) < 0.03  # 最低价接近20日线
                    above_ma20 = close_1day_ago > latest_ma20  # 收盘价在20日线上方
                    
                    # 计算MACD值（简化版）- 这里用收盘价的短期和长期均线差值作为简化的MACD
                    stock_hist['EMA12'] = stock_hist['收盘'].ewm(span=12, adjust=False).mean()
                    stock_hist['EMA26'] = stock_hist['收盘'].ewm(span=26, adjust=False).mean()
                    stock_hist['MACD'] = stock_hist['EMA12'] - stock_hist['EMA26']
                    stock_hist['Signal'] = stock_hist['MACD'].ewm(span=9, adjust=False).mean()
                    stock_hist['Histogram'] = stock_hist['MACD'] - stock_hist['Signal']
                    
                    # 检查MACD柱状图是否由负转正或上升
                    hist_2days_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_2days_ago]['Histogram'].values[0]
                    hist_1day_ago = stock_hist[stock_hist['日期'].astype(str).str.replace("-", "") == date_1day_ago]['Histogram'].values[0]
                    macd_improving = hist_1day_ago > hist_2days_ago
                    macd_turning_positive = hist_1day_ago > 0 and hist_2days_ago < 0
                    
                    # 计算缩量回调特征
                    avg_volume_before_limit = (volume_5days_ago + volume_4days_ago) / 2
                    avg_volume_after_limit = (volume_3days_ago + volume_2days_ago + volume_1day_ago) / 3
                    volume_decreasing = avg_volume_after_limit < avg_volume_before_limit
                    
                    # 计算反转信号 - 最后一个交易日收盘价高于开盘价（阳线）
                    reversal_signal = close_1day_ago > open_1day_ago
                    
                    # 计算反弹力度 - 从最低点到收盘的涨幅
                    min_price_during_pullback = min(low_3days_ago, low_2days_ago, low_1day_ago)
                    rebound_strength = close_1day_ago / min_price_during_pullback - 1
                    
                    # 计算买卖点和预期收益
                    entry_price, stop_loss, target1, target2, expected_return = calculate_entry_exit_points(
                        stock_code, stock_hist, date_4days_ago, date_1day_ago, close_1day_ago
                    )
                    
                    # 计算风险回报比
                    risk_reward = calculate_risk_reward_ratio(entry_price, stop_loss, target1, target2)
                    
                    # 评估市场强度
                    market_strength = evaluate_market_strength(stock_hist, date_1day_ago)
                    
                    # 增强后的龙回头策略条件：
                    # 1. 涨停日前一日有上涨表现（股价强势）
                    # 2. 回调幅度适中（-20% 到 -5% 之间）
                    # 3. 回调过程是缩量的（股价下跌但人气未流失）
                    # 4. 最近交易日有企稳迹象（收盘价高于开盘价或形成带下影线K线）
                    # 5. 价格接近均线支撑位或已在均线上方企稳
                    # 6. MACD有改善或金叉迹象
                    # 7. 风险回报比大于2（高质量交易）
                    if (
                        # 上涨阶段特征
                        pct_chg_5days_ago > 0 and pct_chg_4days_ago > 5 and
                        
                        # 回调幅度特征
                        -0.2 < pullback_pct < -0.05 and
                        
                        # 缩量回调特征
                        volume_decreasing and
                        
                        # 均线支撑特征
                        (close_to_ma10 or close_to_ma20 or above_ma20) and
                        
                        # 反转信号特征 - 增强判断
                        (reversal_signal or 
                         (macd_improving and close_1day_ago > low_1day_ago * 1.01) or 
                         macd_turning_positive) and
                        
                        # 确保反弹力度适中，不是大幅反弹（可能是诱多）
                        0.01 < rebound_strength < 0.05 and
                        
                        # 风险回报比合理
                        (risk_reward is None or risk_reward > 2)
                    ):
                        # 生成K线图
                        print_with_flush(f"正在生成 {stock_code} {stock_name} 的K线图...")
                        chart_path = generate_kline_chart(stock_code, stock_name, today)
                        
                        result_stocks.append({
                            '代码': stock_code,
                            '名称': stock_name,
                            '涨停日': date_4days_ago,
                            '回调幅度': f"{pullback_pct*100:.2f}%",
                            '反弹力度': f"{rebound_strength*100:.2f}%",
                            '推荐买入价': entry_price,
                            '止损价': stop_loss,
                            '目标价1': target1,
                            '目标价2': target2,
                            '预期收益': f"{expected_return}%" if expected_return else "N/A",
                            '风险回报比': risk_reward,
                            '市场强度': market_strength,
                            '5日均线': f"{latest_ma5:.2f}",
                            '10日均线': f"{latest_ma10:.2f}",
                            '20日均线': f"{latest_ma20:.2f}",
                            '均线支撑': "是" if (close_to_ma10 or close_to_ma20) else "否",
                            'MACD改善': "是" if macd_improving else "否",
                            'MACD金叉': "是" if macd_turning_positive else "否",
                            '缩量回调': "是" if volume_decreasing else "否",
                            '反转信号': "是" if reversal_signal else "否",
                            'K线图': chart_path if chart_path else "生成失败"
                        })
                        print_with_flush(f"股票 {stock_code} {stock_name} 符合龙回头条件")
            
            except Exception as e:
                print_with_flush(f"处理股票 {stock_code} 时出错: {e}")
                continue
        
        # 转换为DataFrame
        if result_stocks:
            result_df = pd.DataFrame(result_stocks)
            
            # 显示结果
            print_with_flush(f"\n符合龙回头策略的股票列表（共 {len(result_df)} 只）：")
            print(result_df)
            
            # 保存结果
            output_file = f'dragon_head_stocks_{today}.csv'
            result_df.to_csv(output_file, encoding='utf-8-sig', index=False)
            print_with_flush(f"\n数据已保存到 {output_file}")
        else:
            print_with_flush("没有找到符合龙回头策略的股票")
        
    except Exception as e:
        print_with_flush(f"程序执行出错: {e}")

if __name__ == "__main__":
    main()
