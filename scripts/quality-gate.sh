#!/bin/bash
# 质量门禁（最小可执行版）
set -euo pipefail

cd /Users/yachiyo/Developer/seiswave

echo "[QG] 1/3 语法检查"
python3 -m py_compile $(find seiswave tests -name '*.py')

echo "[QG] 2/3 核心回归"
python3 -m pytest -q tests/test_reporting.py

echo "[QG] 3/3 关键模块测试"
python3 -m pytest -q tests/test_generator_worker.py test_generator.py

echo "[QG] PASS"
