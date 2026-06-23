"""広告費取得の対象期間を決めるユーティリティ。

最大14日（2週間）まで。基準は日本時間（JST）。

CLI引数の解釈:
    （引数なし）          → 前日のみ
    N（整数）            → 前日を末尾とする N 日間（例: 3 → 一昨々日〜前日）
    START END（YYYY-MM-DD）→ START〜END（両端含む）
"""

from datetime import datetime, date, timedelta, timezone

JST = timezone(timedelta(hours=9))
MAX_DAYS = 14


def jst_yesterday() -> date:
    return (datetime.now(JST) - timedelta(days=1)).date()


def parse_date_range(args: list) -> tuple:
    """CLI引数から (start_date, end_date) を返す（両端含む・最大14日にクランプ）。"""
    yesterday = jst_yesterday()

    if not args:
        return yesterday, yesterday

    if len(args) == 1:
        try:
            n = int(args[0])
        except ValueError:
            # 単一の日付指定はその日のみ
            d = date.fromisoformat(args[0])
            return d, d
        n = max(1, min(n, MAX_DAYS))
        return yesterday - timedelta(days=n - 1), yesterday

    start = date.fromisoformat(args[0])
    end = date.fromisoformat(args[1])
    if start > end:
        start, end = end, start
    # 14日を超える場合は末尾(end)基準で14日に丸める
    if (end - start).days > MAX_DAYS - 1:
        start = end - timedelta(days=MAX_DAYS - 1)
    return start, end


def date_list(start: date, end: date) -> list:
    """start〜end（両端含む）の date リスト。"""
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]
