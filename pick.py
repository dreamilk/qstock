import akshare as ak
import concurrent.futures

# 列出a股所有股票
d = ak.stock_zh_a_spot_em()

industry_dict = {}
name_dict = {}

def process_stock(symbol):
    # 获取F10
    f10 = ak.stock_individual_info_em(symbol=symbol)
    # 获取行业信息，需要提取具体值
    industry = f10[f10['item']=='行业']['value'].values[0]
    name = f10[f10['item']=='股票简称']['value'].values[0]

    # 跳过ST
    if 'ST' in name:
        return None

    # 跳过非半导体
    if industry != '半导体':
        return None

    # 跳过创业板
    if symbol.startswith('3'):
        return None

    # 计算市盈率
    pe = ak.stock_value_em(symbol=symbol)
    return symbol, name, pe.iloc[-1]

with concurrent.futures.ThreadPoolExecutor() as executor:
    results = executor.map(process_stock, d['代码'])
    
    for result in results:
        if result is not None:
            print(result)

            symbol, name, pe = result
            name_dict[symbol] = name
            industry_dict[symbol] = pe

print(f"总共{len(industry_dict)}只")

# 计算平均市盈率
total_pe = 0  
total_pb = 0
for symbol, pe in industry_dict.items():
    total_pe += pe['PE(TTM)']
    total_pb += pe['市净率']

average_pe = total_pe / len(industry_dict)
average_pb = total_pb / len(industry_dict)

print(f"平均市盈率: {average_pe}")
print(f"平均市净率: {average_pb}")

for symbol, pe in industry_dict.items():
    if pe['PE(TTM)'] <= average_pe and pe['市净率'] <= average_pb:
        print(f"{name_dict[symbol]}: {pe['PE(TTM)']} {pe['市净率']}")

