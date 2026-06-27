#!/bin/bash
# qstock 每日选股 + 网页发布 (供 cron 调用)
# 用当天日期跑 custom 策略；非交易日无数据会自动跳过。
set -o pipefail
cd /home/admin/qstock || exit 1
source .venv/bin/activate

LOG_DIR=/home/admin/qstock/logs
mkdir -p "$LOG_DIR"
TS=$(date '+%Y%m%d_%H%M%S')
LOG="$LOG_DIR/cron_$TS.log"

# 跑发布脚本（默认日期=今天，10只）
python publish.py -l 10 > "$LOG" 2>&1
rc=$?

# 只保留最近 30 个日志
ls -1t "$LOG_DIR"/cron_*.log 2>/dev/null | tail -n +31 | xargs -r rm -f

# 输出简洁摘要（cron 会保存）
if grep -q "报告已发布" "$LOG"; then
    line=$(grep "报告已发布" "$LOG" | tail -1)
    echo "[OK] qstock 选股已更新网页: $line"
elif grep -q "没有找到符合" "$LOG"; then
    echo "[SKIP] $(date '+%Y-%m-%d') 无符合条件股票（可能非交易日或无命中），网页未更新。"
else
    echo "[ERROR rc=$rc] qstock 运行异常，详见 $LOG"
    tail -5 "$LOG"
fi
