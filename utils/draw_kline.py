import os
import datetime
import akshare as ak
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

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
        
        
        def to_tx_symbol(symbol: str) -> str:
            if symbol.startswith(("sh", "sz")):
                return symbol
            if symbol.startswith("6"):
                return f"sh{symbol}"
            return f"sz{symbol}"

        def normalize_hist_df(df: pd.DataFrame) -> pd.DataFrame:
            if df is None or df.empty:
                return df
            if "日期" in df.columns:
                return df
            if "date" in df.columns:
                out = df.copy()
                out.rename(
                    columns={
                        "date": "日期",
                        "open": "开盘",
                        "close": "收盘",
                        "high": "最高",
                        "low": "最低",
                        "amount": "成交量",
                    },
                    inplace=True,
                )
                return out
            return df

        try:
            hist_data = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date_str,
                end_date=end_date_str,
                adjust="qfq",
                timeout=10,
            )
        except Exception:
            hist_data = ak.stock_zh_a_hist_tx(
                symbol=to_tx_symbol(stock_code),
                start_date=start_date_str,
                end_date=end_date_str,
                adjust="qfq",
                timeout=10,
            )

        hist_data = normalize_hist_df(hist_data)
        
        # 检查数据量是否足够
        if len(hist_data) < 5:
            print(f"股票 {stock_code} 的K线图数据不足，跳过绘图")
            return None
            
        # 确保有数据
        if hist_data.empty:
            print(f"股票 {stock_code} 在指定时间范围内没有数据，跳过绘图")
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
        
        print(f"已保存K线图: {filepath}")
        return filepath
    except Exception as e:
        print(f"生成股票 {stock_code} K线图时出错: {e}")
        return None
