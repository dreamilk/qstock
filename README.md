# qstock

A stock screening tool for Chinese A-shares that implements technical analysis strategies.

## Description

qstock is a Python-based tool that helps identify trading opportunities in the Chinese stock market by applying technical analysis strategies. The tool analyzes historical stock data, identifies specific price patterns, and generates candlestick charts for visual confirmation.

## Features

- Multi-strategy stock screening（龙回头 / 涨停板 / 自定义复合 / 低估值）
- Fetches and processes historical stock data using akshare API
- Generates candlestick charts with moving averages for visual analysis
- Exports results to CSV files for further analysis
- KDJ strategy backtesting with pybroker
- Web-based report publishing via nginx
- Command-line interface for flexible usage

## Requirements

- Python 3.9+
- Required packages: see `requirements.txt`

## Installation

1. Clone this repository:

```bash
git clone https://github.com/dreamilk/qstock.git
cd qstock
```

2. Create venv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Stock Screening

```bash
# 默认使用 custom 策略
python pick.py

# 指定策略和数量
python pick.py -s dragonhead -l 5

# 指定日期
python pick.py -d 20260625
```

### Publish to Web

```bash
# 运行选股并发布到 nginx 静态博客
python publish.py

# 一键运行
./run.sh
```

### Backtesting

```bash
# KDJ 策略回测（需要 pybroker）
pip install pybroker
python broker.py
```

### Run Tests

```bash
pytest tests/ -v
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
