#!/bin/bash
# 一键运行选股并发布到网页博客
# 用法: ./run.sh [日期YYYYMMDD] [数量]
cd "$(dirname "$0")"
source .venv/bin/activate
DATE="${1:-}"
LIMIT="${2:-10}"
if [ -n "$DATE" ]; then
    python publish.py -d "$DATE" -l "$LIMIT"
else
    python publish.py -l "$LIMIT"
fi
