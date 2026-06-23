#!/bin/bash
# ローカル毎朝実行（ASP + Yahoo広告）。launchd から呼ばれる。
set -euo pipefail

PROJECT_DIR="/Users/mitomi/Claude/daily-report-automation"
PYTHON="/usr/local/Caskroom/miniconda/base/bin/python"

cd "$PROJECT_DIR"
exec "$PYTHON" -m phase1.run_local
