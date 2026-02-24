#!/bin/bash
# dispatch-claude.sh — 异步派发任务到 Claude Code（零轮询）
# 新增：并行锁 + task_id + 质量门禁提示

set -euo pipefail

PROJECT_DIR="/Users/yachiyo/Developer/seiswave"
RESULTS_DIR="${PROJECT_DIR}/.claude/results"
LOG_DIR="${PROJECT_DIR}/.claude/logs"
LOCKS_DIR="${RESULTS_DIR}/locks"

usage() {
  cat <<'EOF'
用法:
  ./scripts/dispatch-claude.sh "任务描述" [选项]

选项:
  --lock-key <key>      并行锁键（默认: default）
  --no-quality-gate     不自动附加质量门禁要求
  --model <model>       Claude Code 模型（默认: opus）
  --permission-mode <m> 权限模式（默认: bypassPermissions）
EOF
}

TASK_PROMPT="${1:-}"
if [ -z "$TASK_PROMPT" ]; then
  usage
  exit 1
fi
shift || true

LOCK_KEY="default"
USE_QUALITY_GATE="true"
MODEL="opus"
PERMISSION_MODE="bypassPermissions"

EXTRA_ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --lock-key)
      LOCK_KEY="${2:-default}"
      shift 2
      ;;
    --no-quality-gate)
      USE_QUALITY_GATE="false"
      shift
      ;;
    --model)
      MODEL="${2:-opus}"
      shift 2
      ;;
    --permission-mode)
      PERMISSION_MODE="${2:-bypassPermissions}"
      shift 2
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

mkdir -p "$RESULTS_DIR" "$LOG_DIR" "$LOCKS_DIR"

TASK_ID="tsk_$(date +%Y%m%d_%H%M%S)_$RANDOM"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/claude_${TIMESTAMP}_${TASK_ID}.log"
LOCK_DIR="${LOCKS_DIR}/${LOCK_KEY}.lock"
LOCK_META="${LOCK_DIR}/meta.json"

# 并行锁：同 lock-key 只允许一个任务运行（含僵尸锁清理）
if [ -d "$LOCK_DIR" ]; then
  if [ -f "$LOCK_META" ]; then
    OLD_PID=$(python3 - <<'PY' "$LOCK_META"
import json,sys
try:
  print(json.load(open(sys.argv[1])).get('pid',''))
except Exception:
  print('')
PY
)
    if [ -n "$OLD_PID" ] && ps -p "$OLD_PID" >/dev/null 2>&1; then
      echo "❌ 并行锁冲突: lock-key='${LOCK_KEY}' 正在运行 (pid=${OLD_PID})"
      echo "查看: ${LOCK_META}"
      exit 2
    else
      rm -rf "$LOCK_DIR"
    fi
  else
    rm -rf "$LOCK_DIR"
  fi
fi

mkdir -p "$LOCK_DIR"

FINAL_PROMPT="$TASK_PROMPT"
if [ "$USE_QUALITY_GATE" = "true" ]; then
  FINAL_PROMPT="${FINAL_PROMPT}

【强制质量门禁】
修改完成后必须执行：
  bash scripts/quality-gate.sh
并在最终回复中给出质量门禁结果（通过/失败、关键输出）。"
fi

echo "🚀 派发任务到 Claude Code..."
echo "🆔 task_id: ${TASK_ID}"
echo "🔒 lock_key: ${LOCK_KEY}"
echo "🧠 model: ${MODEL}"
echo "📁 目录: ${PROJECT_DIR}"
echo "📝 日志: ${LOG_FILE}"

cd "$PROJECT_DIR"
nohup claude -p \
  --model "$MODEL" \
  --permission-mode "$PERMISSION_MODE" \
  --append-system-prompt "TASK_ID=${TASK_ID}; LOCK_KEY=${LOCK_KEY}; 在最终总结中必须包含 TASK_ID。" \
  "${FINAL_PROMPT}" \
  > "$LOG_FILE" 2>&1 &

CLAUDE_PID=$!

cat > "$LOCK_META" <<EOF
{"task_id":"${TASK_ID}","pid":${CLAUDE_PID},"lock_key":"${LOCK_KEY}","log_file":"${LOG_FILE}","created_at":"$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")"}
EOF

cat > "${RESULTS_DIR}/.current_task.json" <<EOF
{"task_id":"${TASK_ID}","pid":${CLAUDE_PID},"lock_key":"${LOCK_KEY}","log_file":"${LOG_FILE}","started_at":"$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")"}
EOF

echo "✅ Claude Code 已启动 (PID: ${CLAUDE_PID})"
echo "⏳ 后台运行中；Hook 完成后会写入 results 并唤醒 OpenClaw"
echo "📊 tail -f ${LOG_FILE}"
echo "🔍 cat ${RESULTS_DIR}/latest.json"
