# qstock

A stock screening tool for Chinese A-shares that implements technical analysis strategies.

## Description

qstock is a Python-based tool that helps identify trading opportunities in the Chinese stock market by applying technical analysis strategies, particularly the "Dragon Head" (龙回头) strategy. The tool analyzes historical stock data, identifies specific price patterns, and generates candlestick charts for visual confirmation.

## Features

- Automatic screening of A-shares based on the Dragon Head strategy
- Fetches and processes historical stock data using akshare API
- Generates candlestick charts with moving averages for visual analysis
- Exports results to CSV files for further analysis
- Command-line interface for flexible usage

## Requirements

- Python 3.6+
- Required packages:
  - akshare
  - pandas
  - matplotlib
  - mplfinance
  - requests
  - argparse

## Installation

1. Clone this repository:

```bash
git clone https://github.com/yourusername/qstock.git
cd qstock
```

2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

```bash
python pick.py
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

