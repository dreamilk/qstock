#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选股发布脚本
============
运行 qstock 选股策略，将结果生成 Markdown + HTML 报告（含 K 线图），
保存到 nginx 静态目录的带时间戳子目录，并重建博客式索引页。

用法:
    python publish.py [-d YYYYMMDD] [-s strategy] [-l limit]

输出目录: /usr/share/nginx/html/qstock/
    index.html              博客首页（报告列表）
    runs/<run_id>/
        index.html          单次报告页
        report.md           markdown 结果
        custom_stocks_*.csv  原始 csv
        charts/*.png        K 线图
"""
import os
import sys
import json
import shutil
import argparse
import datetime
import subprocess

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

# 发布目录
PUBLISH_ROOT = "/usr/share/nginx/html/qstock"
RUNS_DIR = os.path.join(PUBLISH_ROOT, "runs")


def run_screening(date, strategy, limit, filter_stocks):
    """运行选股策略，返回 (DataFrame, charts_dir, csv_path)"""
    import akshare as ak
    from strategy import get_strategy, toDataFrame
    from utils.draw_kline import generate_kline_chart

    print(f"akshare 版本: {ak.__version__}")
    print(f"日期={date} 策略={strategy} 数量={limit}")

    strat = get_strategy(strategy)
    result_stocks = strat.filter_stocks(date, limit_stock_count=int(limit),
                                        filter_stocks=filter_stocks)

    if not result_stocks:
        return None, None, None, strat.name

    result_df = toDataFrame(result_stocks)

    # 为本次运行创建独立工作目录的 charts
    run_charts = os.path.join(PROJECT_DIR, "_tmp_charts")
    if os.path.exists(run_charts):
        shutil.rmtree(run_charts)
    os.makedirs(run_charts, exist_ok=True)

    # 生成 K 线图（带重试）
    for _, row in result_df.iterrows():
        for attempt in range(3):
            try:
                path = generate_kline_chart(row['code'], row['name'], date,
                                            output_dir=run_charts)
                if path:
                    break
            except Exception as e:
                print(f"K线图 {row['code']} 第{attempt+1}次失败: {e}")

    # 保存 csv
    csv_path = os.path.join(PROJECT_DIR, f'{strat.name}_stocks_{date}.csv')
    result_df.to_csv(csv_path, encoding='utf-8-sig', index=False)

    return result_df, run_charts, csv_path, strat.name


def df_to_markdown(df, date, strategy_name, generated_at):
    """把结果 DataFrame 渲染成 markdown"""
    lines = []
    lines.append(f"# 选股报告 · {strategy_name} 策略")
    lines.append("")
    lines.append(f"- **选股日期**: {date}")
    lines.append(f"- **生成时间**: {generated_at}")
    lines.append(f"- **命中数量**: {len(df)} 只")
    lines.append("")
    lines.append("## 结果汇总")
    lines.append("")
    lines.append("| 排名 | 代码 | 名称 | 现价 | 买入价 | 卖出价 | 评分 |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, row in df.iterrows():
        lines.append(f"| {i+1} | {row['code']} | {row['name']} | "
                     f"{row.get('current_price','')} | {row.get('buy_price','')} | "
                     f"{row.get('sell_price','')} | {row.get('score','')} |")
    lines.append("")
    lines.append("## 个股详情")
    lines.append("")
    for i, row in df.iterrows():
        lines.append(f"### {i+1}. {row['code']} {row['name']}  （评分 {row.get('score','')}）")
        lines.append("")
        lines.append(f"> {row.get('suggest_reason','')}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*本报告由 qstock 自动生成，仅供研究参考，不构成任何投资建议。*")
    return "\n".join(lines)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{ --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#e6edf3;
  --muted:#8b949e; --accent:#58a6ff; --up:#f85149; --down:#3fb950; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  line-height:1.7; }}
.container {{ max-width:980px; margin:0 auto; padding:32px 20px 80px; }}
header.site {{ border-bottom:1px solid var(--border); padding-bottom:20px; margin-bottom:32px; }}
header.site h1 {{ margin:0 0 6px; font-size:26px; }}
header.site p {{ margin:0; color:var(--muted); font-size:14px; }}
a {{ color:var(--accent); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.meta {{ color:var(--muted); font-size:14px; margin-bottom:24px; }}
.meta span {{ margin-right:18px; }}
table {{ width:100%; border-collapse:collapse; margin:16px 0 32px; font-size:14px; }}
th,td {{ border:1px solid var(--border); padding:9px 12px; text-align:center; }}
th {{ background:var(--card); color:var(--accent); }}
tr:nth-child(even) td {{ background:rgba(255,255,255,0.02); }}
h2 {{ border-left:3px solid var(--accent); padding-left:10px; margin-top:40px; }}
.stock-card {{ background:var(--card); border:1px solid var(--border);
  border-radius:10px; padding:20px; margin-bottom:28px; }}
.stock-card h3 {{ margin:0 0 6px; font-size:18px; }}
.stock-card .badge {{ background:var(--accent); color:#0d1117; border-radius:6px;
  padding:2px 8px; font-size:12px; font-weight:600; margin-left:8px; }}
.stock-card .reason {{ color:var(--muted); font-size:14px; margin:10px 0; }}
.stock-card img {{ width:100%; border-radius:8px; border:1px solid var(--border); margin-top:10px; }}
.no-chart {{ color:var(--muted); font-size:13px; font-style:italic; }}
.back {{ display:inline-block; margin-bottom:24px; }}
footer {{ margin-top:48px; padding-top:20px; border-top:1px solid var(--border);
  color:var(--muted); font-size:13px; }}
.disclaimer {{ background:rgba(248,81,73,0.08); border:1px solid rgba(248,81,73,0.3);
  border-radius:8px; padding:12px 16px; font-size:13px; color:#f0a0a0; margin-top:30px; }}
ul.runlist {{ list-style:none; padding:0; }}
ul.runlist li {{ background:var(--card); border:1px solid var(--border);
  border-radius:10px; padding:16px 20px; margin-bottom:14px; display:flex;
  justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }}
ul.runlist .info {{ font-size:14px; }}
ul.runlist .date {{ font-size:17px; font-weight:600; }}
ul.runlist .sub {{ color:var(--muted); font-size:13px; }}
.count-pill {{ background:var(--accent); color:#0d1117; border-radius:20px;
  padding:3px 12px; font-size:13px; font-weight:600; }}
</style>
</head>
<body>
<div class="container">
{body}
</div>
</body>
</html>
"""


def build_report_html(df, charts_files, date, strategy_name, generated_at):
    rows = ""
    for i, row in df.iterrows():
        rows += (f"<tr><td>{i+1}</td><td>{row['code']}</td><td>{row['name']}</td>"
                 f"<td>{row.get('current_price','')}</td><td>{row.get('buy_price','')}</td>"
                 f"<td>{row.get('sell_price','')}</td><td>{row.get('score','')}</td></tr>")

    cards = ""
    for i, row in df.iterrows():
        code = str(row['code'])
        # 匹配该股票的图
        img_html = '<p class="no-chart">（本次未能生成 K 线图，可能因数据源临时不可用）</p>'
        for fn in charts_files:
            if code in fn:
                img_html = f'<img src="charts/{fn}" alt="{code} K线图">'
                break
        cards += (f'<div class="stock-card">'
                  f'<h3>{i+1}. {row["code"]} {row["name"]}'
                  f'<span class="badge">评分 {row.get("score","")}</span></h3>'
                  f'<div class="reason">{row.get("suggest_reason","")}</div>'
                  f'{img_html}</div>')

    body = f"""<header class="site">
  <h1>📈 选股报告 · {strategy_name} 策略</h1>
  <p>qstock 量化选股系统自动生成</p>
</header>
<a class="back" href="../../index.html">← 返回报告列表</a>
<div class="meta">
  <span>📅 选股日期：<b>{date}</b></span>
  <span>🕐 生成时间：{generated_at}</span>
  <span>🎯 命中：<b>{len(df)}</b> 只</span>
</div>
<h2>结果汇总</h2>
<table>
<tr><th>排名</th><th>代码</th><th>名称</th><th>现价</th><th>买入价</th><th>卖出价</th><th>评分</th></tr>
{rows}
</table>
<h2>个股详情</h2>
{cards}
<div class="disclaimer">⚠️ 本报告由程序自动生成，仅供研究与学习参考，不构成任何投资建议。股市有风险，入市需谨慎。</div>
<footer>Generated by qstock · {generated_at}</footer>"""

    return HTML_TEMPLATE.format(title=f"选股报告 {date} · {strategy_name}", body=body)


def build_index_html():
    """扫描 runs 目录，重建博客式索引页"""
    runs = []
    if os.path.isdir(RUNS_DIR):
        for rid in sorted(os.listdir(RUNS_DIR), reverse=True):
            meta_path = os.path.join(RUNS_DIR, rid, "meta.json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, encoding="utf-8") as f:
                        runs.append(json.load(f))
                except Exception:
                    pass

    items = ""
    for m in runs:
        items += (f'<li><div class="info">'
                  f'<div class="date">📅 {m["date"]} · {m["strategy"]}</div>'
                  f'<div class="sub">生成于 {m["generated_at"]}</div></div>'
                  f'<div><span class="count-pill">{m["count"]} 只</span> '
                  f'&nbsp;<a href="runs/{m["run_id"]}/index.html">查看报告 →</a></div></li>')

    if not items:
        items = '<li><div class="info">暂无报告，运行 publish.py 后生成。</div></li>'

    body = f"""<header class="site">
  <h1>📊 量化选股博客</h1>
  <p>qstock · 涨停回调策略 · 每次运行自动归档</p>
</header>
<p class="meta">共 {len(runs)} 份报告 · 最新更新 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<ul class="runlist">
{items}
</ul>
<div class="disclaimer">⚠️ 所有报告由程序自动生成，仅供研究参考，不构成投资建议。</div>
<footer>Powered by qstock + akshare · nginx static blog</footer>"""

    html = HTML_TEMPLATE.format(title="量化选股博客 · qstock", body=body)
    with open(os.path.join(PUBLISH_ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已重建索引页: {PUBLISH_ROOT}/index.html  (共 {len(runs)} 份报告)")


def main():
    parser = argparse.ArgumentParser(description='选股并发布到网页')
    parser.add_argument('-d', '--date', default=None, help='日期 YYYYMMDD')
    parser.add_argument('-s', '--strategy', default='custom', help='策略')
    parser.add_argument('-l', '--limit', default=10, help='数量')
    parser.add_argument('-f', '--filter', default=True)
    args = parser.parse_args()

    date = args.date or datetime.datetime.now().strftime('%Y%m%d')
    generated_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    df, charts_dir, csv_path, strat_name = run_screening(
        date, args.strategy, args.limit, args.filter)

    if df is None or len(df) == 0:
        print(f"没有找到符合 {strat_name} 策略的股票，跳过发布。")
        return

    # 创建本次运行目录
    run_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + f"_{strat_name}"
    run_dir = os.path.join(RUNS_DIR, run_id)
    run_charts_out = os.path.join(run_dir, "charts")
    os.makedirs(run_charts_out, exist_ok=True)

    # 拷贝图表
    charts_files = []
    if charts_dir and os.path.isdir(charts_dir):
        for fn in os.listdir(charts_dir):
            shutil.copy2(os.path.join(charts_dir, fn),
                         os.path.join(run_charts_out, fn))
            charts_files.append(fn)

    # 拷贝 csv
    if csv_path and os.path.isfile(csv_path):
        shutil.copy2(csv_path, os.path.join(run_dir, os.path.basename(csv_path)))

    # markdown
    md = df_to_markdown(df.reset_index(drop=True), date, strat_name, generated_at)
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)

    # html
    html = build_report_html(df.reset_index(drop=True), charts_files,
                             date, strat_name, generated_at)
    with open(os.path.join(run_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # meta
    meta = {"run_id": run_id, "date": date, "strategy": strat_name,
            "count": int(len(df)), "generated_at": generated_at}
    with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 重建索引
    build_index_html()

    print(f"\n✅ 报告已发布: {run_dir}")
    print(f"   网页查看: http://<服务器>/qstock/runs/{run_id}/index.html")
    print(f"   博客首页: http://<服务器>/qstock/index.html")


if __name__ == "__main__":
    main()
