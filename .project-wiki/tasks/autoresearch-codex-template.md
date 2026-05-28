# SeisWave AutoResearch Template

适用场景：核心算法修复、选波逻辑调整、Fortran/Python 桥接问题、测试补强。

## 通用命令

```bash
cd /Users/yachiyo/Developer/seiswave
python3 /Users/yachiyo/.openclaw/workspace/skills/agent-wiki/scripts/autoresearch.py \
  "修复 <问题描述>，仅修改最小必要范围，并保持现有 API 行为稳定" \
  --project /Users/yachiyo/Developer/seiswave \
  --criteria "相关 pytest 用例通过，且无新增失败" \
  --max-iter 3 \
  --test-cmd "pytest tests/test_core.py tests/test_selector.py tests/test_fortran.py -q" \
  --agent codex
```

## 典型任务 1：选波器逻辑问题

```bash
cd /Users/yachiyo/Developer/seiswave
python3 /Users/yachiyo/.openclaw/workspace/skills/agent-wiki/scripts/autoresearch.py \
  "修复 selector 相关缺陷，优先检查 seiswave/core/selector.py 与 tests/test_selector.py，先让失败测试稳定重现，再修复实现" \
  --project /Users/yachiyo/Developer/seiswave \
  --criteria "tests/test_selector.py 全部通过" \
  --max-iter 3 \
  --test-cmd "pytest tests/test_selector.py -q" \
  --agent codex
```

## 典型任务 2：Fortran 桥接/回退问题

```bash
cd /Users/yachiyo/Developer/seiswave
python3 /Users/yachiyo/.openclaw/workspace/skills/agent-wiki/scripts/autoresearch.py \
  "修复 fortran_bridge 的兼容性或回退路径问题，保持 Python fallback 可用，避免破坏现有接口" \
  --project /Users/yachiyo/Developer/seiswave \
  --criteria "tests/test_fortran.py 通过，且相关 core 测试不回归" \
  --max-iter 3 \
  --test-cmd "pytest tests/test_fortran.py tests/test_core.py -q" \
  --agent codex
```

## 建议工作流

1. 先查询 wiki：
   `python3 /Users/yachiyo/.openclaw/workspace/skills/agent-wiki/scripts/wiki_manager.py query "selector fortran tests" --project /Users/yachiyo/Developer/seiswave`
2. 再运行 AutoResearch。
3. 完成后补一条 `.project-wiki/tasks/` 记录。
