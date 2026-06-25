#!/bin/bash
# CSV生成リクエスト監視（launchdから数分おきに呼ばれる・1回実行型）。
set -euo pipefail

PROJECT_DIR="/Users/mitomi/Claude/daily-report-automation"
PYTHON="/usr/local/Caskroom/miniconda/base/bin/python"

cd "$PROJECT_DIR"
exec "$PYTHON" -m phase2.request_watcher
