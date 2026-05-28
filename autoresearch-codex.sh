#!/usr/bin/env bash
# SeisWave AutoResearch 快捷入口
# Use: ./autoresearch-codex.sh <mode> [extra description]
# modes: selector / fortran / combiner / reporting / core / all
# 用法：./autoresearch-codex.sh <模式> [额外描述]
# 模式：selector / fortran / combiner / reporting / core / all

set -euo pipefail
PROJECT="/Users/yachiyo/Developer/seiswave"
SCRIPT="/Users/yachiyo/.openclaw/workspace/skills/agent-wiki/scripts/autoresearch.py"
AGENT="${AUTO_AGENT:-codex}"

cd "$PROJECT"

mode="${1:-}"
desc="${2:-}"

case "$mode" in
  selector)
    python3 "$SCRIPT" \
      "修复 selector 相关缺陷${desc:+，}${desc}。优先检查 seiswave/core/selector.py 与 tests/test_selector.py，先让失败测试稳定重现，再修复实现。仅修改最小必要范围。" \
      --project "$PROJECT" \
      --criteria "tests/test_selector.py 全部通过" \
      --max-iter 3 \
      --test-cmd "python3 -m pytest tests/test_selector.py -q" \
      --agent "$AGENT"
    ;;
  fortran)
    python3 "$SCRIPT" \
      "修复 fortran_bridge 的兼容性或回退路径问题${desc:+，}${desc}。保持 Python fallback 可用，避免破坏现有接口。" \
      --project "$PROJECT" \
      --criteria "tests/test_fortran.py 通过，且 core 测试不回归" \
      --max-iter 3 \
      --test-cmd "python3 -m pytest tests/test_fortran.py tests/test_core.py -q" \
      --agent "$AGENT"
    ;;
  combiner)
    python3 "$SCRIPT" \
      "修复 combiner 相关缺陷${desc:+，}${desc}。优先检查 seiswave/core/combiner.py 与 tests/test_combiner.py。" \
      --project "$PROJECT" \
      --criteria "tests/test_combiner.py 全部通过" \
      --max-iter 3 \
      --test-cmd "python3 -m pytest tests/test_combiner.py -q" \
      --agent "$AGENT"
    ;;
  reporting)
    python3 "$SCRIPT" \
      "修复 reporting 相关缺陷${desc:+，}${desc}。优先检查 seiswave/core/reporting.py 以及 reporting 相关测试，保持汇总字段兼容。" \
      --project "$PROJECT" \
      --criteria "reporting 相关测试全部通过" \
      --max-iter 3 \
      --test-cmd "python3 -m pytest tests/test_reporting.py tests/test_reporting_edge.py tests/test_reporting_more.py -q" \
      --agent "$AGENT"
    ;;
  core)
    python3 "$SCRIPT" \
      "修复核心模块缺陷${desc:+，}${desc}。优先检查 seiswave/core/ 下的相关模块与 tests/test_core.py。" \
      --project "$PROJECT" \
      --criteria "tests/test_core.py 通过" \
      --max-iter 3 \
      --test-cmd "python3 -m pytest tests/test_core.py -q" \
      --agent "$AGENT"
    ;;
  all)
    python3 "$SCRIPT" \
      "修复项目中的缺陷${desc:+，}${desc}。保持现有 API 行为稳定，最小化改动。" \
      --project "$PROJECT" \
      --criteria "相关 pytest 用例通过，且无新增失败" \
      --max-iter 3 \
      --test-cmd "python3 -m pytest tests/ -q" \
      --agent "$AGENT"
    ;;
  *)
    echo "用法: $0 <模式> [额外描述]"
    echo ""
    echo "可用模式:"
    echo "  selector  - 选波器问题"
    echo "  fortran   - Fortran 桥接问题"
    echo "  combiner  - 组合器问题"
    echo "  reporting - 汇总/报告问题"
    echo "  core      - 核心模块问题"
    echo "  all       - 全量测试"
    echo ""
    echo "示例:"
    echo "  $0 selector \"处理边界条件异常\""
    echo "  $0 fortran \"macOS Sonoma 兼容性\""
    echo ""
    echo "可用环境变量:"
    echo "  AUTO_AGENT=codex|opencode|claude  (默认 codex)"
    exit 1
    ;;
esac
