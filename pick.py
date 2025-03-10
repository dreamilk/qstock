import akshare as ak
import datetime
import sys
import argparse  # Add argparse for command-line arguments
from utils.draw_kline import generate_kline_chart

# Import the strategy factory
from strategy import get_strategy, toDataFrame

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


# 主程序
def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='股票筛选工具')
    parser.add_argument('-d', '--date', help='指定日期 (格式: YYYYMMDD)', default=None)
    parser.add_argument('-s', '--strategy', help='选股策略 (默认: dragonhead, hit_board, custom)', default='dragonhead')
    parser.add_argument('-l', '--limit', help='限制股票数量 (默认: 5)', default=10)
    parser.add_argument('-f', '--filter', help='是否过滤创业板、科创板、ST股 (默认: True)', default=True)
    args = parser.parse_args()
    
    # 设置日期
    if args.date:
        today = args.date
        print_with_flush(f"使用指定日期: {today}")
    else:
        today = datetime.datetime.now().strftime('%Y%m%d')
        print_with_flush(f"使用今日日期: {today}")
    
    try:
        print_with_flush(f"使用策略: {args.strategy}")

        strategy = get_strategy(args.strategy)
        
        # 筛选股票
        result_stocks = strategy.filter_stocks(today, limit_stock_count=int(args.limit), filter_stocks=args.filter)
        
        # 转换为DataFrame
        if result_stocks:
            result_df = toDataFrame(result_stocks)
            
            # 显示结果
            print_with_flush(f"\n符合{strategy.name}策略的股票列表（共 {len(result_df)} 只）：")
            print(result_df)

            # 生成K线图
            for index, row in result_df.iterrows():
                generate_kline_chart(row['code'], row['name'], today)
            
            # 保存结果
            output_file = f'{strategy.name}_stocks_{today}.csv'
            result_df.to_csv(output_file, encoding='utf-8-sig', index=False)
            print_with_flush(f"\n数据已保存到 {output_file}")
        else:
            print_with_flush(f"没有找到符合{strategy.name}策略的股票")
        
    except Exception as e:
        print_with_flush(f"程序执行出错: {e}")

if __name__ == "__main__":
    main()
