"""ローカル毎朝実行用の統合ランナー（ASP + Yahoo広告）。

GitHub Actionsのクラウドからは提供元APIにIPブロックされるため、
ASP（Playwright）とYahoo広告はローカル（Mac）で実行する。
launchd から毎朝呼び出す想定。

実行:
    python -m phase1.run_local
ログ:
    logs/run_local_YYYY-MM-DD.log
"""

import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# invahamo は INVGOLD に統合済みのため対象外
SKIP_ASPS = {"invahamo"}


def setup_logging() -> str:
    date_str = (datetime.now(JST) - timedelta(days=1)).date().isoformat()
    os.makedirs("logs", exist_ok=True)
    log_path = f"logs/run_local_{date_str}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return date_str


def list_asp_targets() -> list:
    import yaml

    with open("config/asp_sites.yaml", encoding="utf-8") as f:
        sites = yaml.safe_load(f)["asp_sites"]
    return [n for n in sites.keys() if n not in SKIP_ASPS]


def run_asp(date_str: str) -> tuple[int, int]:
    """ASPを1社ごとに別プロセスで実行する。

    Playwright(同期API)は1プロセスで複数回起動できない（2社目以降が
    "event loop already running" で失敗する）ため、サブプロセスで分離する。
    戻り値: (成功数, 失敗数)
    """
    import subprocess

    log = logging.getLogger("asp")
    ok = 0
    fail = 0
    for name in list_asp_targets():
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "phase1.asp_downloader", name, date_str],
                capture_output=True, text=True, timeout=300,
            )
            out = (proc.stdout or "").strip().splitlines()
            tail = out[-1] if out else ""
            if proc.returncode == 0:
                log.info(f"{name}: {tail or 'OK'}")
                if "スキップ" not in tail:
                    ok += 1
            else:
                err = (proc.stderr or "").strip().splitlines()
                log.error(f"{name}: 失敗 (rc={proc.returncode}) {tail} {err[-1] if err else ''}")
                fail += 1
        except subprocess.TimeoutExpired:
            log.error(f"{name}: タイムアウト")
            fail += 1
        except Exception as e:
            log.error(f"{name}: 起動失敗 → {e}")
            fail += 1
    return ok, fail


def run_yahoo(uploader, date_str: str) -> bool:
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    log = logging.getLogger("yahoo")
    try:
        fetcher = YahooAdsFetcher()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp = f.name
        fetcher.fetch_to_csv(tmp)
        file_id = uploader.upload_csv(tmp, "yahoo_ads.csv", date_str)
        os.unlink(tmp)
        log.info(f"Yahoo: アップロード完了 yahoo_ads.csv ({file_id})")
        return True
    except Exception as e:
        log.error(f"Yahoo: 失敗 → {e}")
        return False


def main():
    date_str = setup_logging()
    log = logging.getLogger("main")
    log.info(f"=== ローカル実行開始 対象日={date_str} ===")

    # 1) ASPは1社ごとに別プロセスで実行（Playwright同期APIの再起動制約のため）
    asp_ok, asp_fail = run_asp(date_str)

    # 2) Yahooは同プロセスでOK（Playwright不使用）
    from phase1.drive_uploader import DriveUploader

    uploader = DriveUploader()
    yahoo_ok = run_yahoo(uploader, date_str)

    log.info(
        f"=== 完了 ASP成功{asp_ok}/失敗{asp_fail} / Yahoo={'OK' if yahoo_ok else 'NG'} ==="
    )
    # ASP/Yahooのいずれかが全滅なら異常終了（launchdのログで気づけるように）
    if asp_ok == 0 and not yahoo_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
