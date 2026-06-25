"""CSV生成リクエストの監視・処理（ボタン連携のMac側）。

スプレッドシートの「CSV生成リクエスト」タブを確認し、status='pending' の依頼に対して
担当者別CSV(build_personal_split)を生成、ステータスを更新する。

launchd の StartInterval で数分おきに実行する想定（常駐ループではなく1回実行型）。

実行:
    python -m phase2.request_watcher
"""

import logging
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAX_DAYS = 14


def _parse_date(s: str):
    s = str(s).strip().replace("-", "/")
    try:
        y, m, d = [int(x) for x in s.split("/")]
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def _resolve_range(start_s, end_s):
    start = _parse_date(start_s)
    end = _parse_date(end_s)
    if not start and not end:
        return None, None
    start = start or end
    end = end or start
    if start > end:
        start, end = end, start
    if (end - start).days > MAX_DAYS - 1:
        start = end - timedelta(days=MAX_DAYS - 1)
    return start, end


def process_once() -> int:
    """pending依頼を1巡処理する。処理した件数を返す。"""
    from phase1.drive_uploader import DriveUploader
    from phase2.sheet_reader import SheetReader
    from phase2.build_personal_split import PersonalSplitter, generate_for_person

    reader = SheetReader()
    pending = reader.read_pending_requests()
    if not pending:
        return 0

    logger.info(f"pending依頼: {len(pending)}件")
    uploader = DriveUploader()
    splitter = PersonalSplitter()
    assignments = reader.read_assignments()

    processed = 0
    for req in pending:
        row, person = req["row"], req["person"]
        reader.update_request_status(row, "処理中")
        try:
            start, end = _resolve_range(req["start"], req["end"])
            if not start:
                reader.update_request_status(row, "エラー", "取得日が不正です")
                continue
            assignment = assignments.get(person)
            if assignment is None:
                reader.update_request_status(
                    row, "エラー", f"担当者 '{person}' のシートが見つかりません"
                )
                continue
            made = generate_for_person(uploader, splitter, person, assignment, start, end)
            msg = f"{len(made)}ファイル生成（{start}〜{end}）"
            reader.update_request_status(row, "完了", msg)
            logger.info(f"  {person}: {msg}")
            processed += 1
        except Exception as e:
            logger.error(f"  {person}: 失敗 → {e}")
            reader.update_request_status(row, "エラー", str(e)[:200])
    return processed


def main():
    n = process_once()
    logger.info(f"処理完了: {n}件" if n else "pending依頼なし")


if __name__ == "__main__":
    main()
