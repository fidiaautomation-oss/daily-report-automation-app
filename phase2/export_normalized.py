"""ASP生CSV(cp932・各社別フォーマット)を正規化し、UTF-8の統一CSVをDriveへ出力する。

Apps Scriptの「CSVデータ作成」ボタンは生のASP CSV(Shift-JIS)を扱えないため、
Pythonが毎朝のうちに正規化済みのUTF-8データを用意しておく。

出力: raw/<日付>/asp_normalized.csv
  列: date, asp_name, case_name, promo_id, site_name, site_id, reward, count
  （広告費 google_ads.csv / yahoo_ads.csv は既にUTF-8のため変換不要）

実行:
    python -m phase2.export_normalized            # シートの取得日範囲 or 前日
    python -m phase2.export_normalized 3          # 直近3日
    python -m phase2.export_normalized 2026-06-15 2026-06-18
"""

import io
import os
import sys
import logging
import tempfile

import pandas as pd
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

NORMALIZED_COLUMNS = [
    "date", "asp_name", "case_name", "promo_id", "site_name", "site_id",
    "reward", "count",
]


def build_normalized_asp(raw_files: dict) -> pd.DataFrame:
    """raw CSV群({ファイル名: bytes})からASP正規化DataFrameを作る。"""
    from phase2.personal_csv_builder import PersonalCsvBuilder

    builder = PersonalCsvBuilder()
    df = builder.normalize_asp(raw_files)
    if df.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)
    # 件数列（1成果=1件）を付与し、列順を統一
    df = df.copy()
    df["count"] = 1
    for col in NORMALIZED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[NORMALIZED_COLUMNS]


def export_for_date(uploader, date_str: str) -> int:
    """指定日のraw ASPを正規化し asp_normalized.csv をDriveへ保存。行数を返す。"""
    raw_files = uploader.download_folder_csvs(date_str, top_folder="raw")
    df = build_normalized_asp(raw_files)
    # 対象日のみに絞る（rawには複数日が混在しない想定だが念のため日付頭一致）
    if len(df):
        df = df[df["date"].astype(str).str.strip().str[:10] == date_str]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp = f.name
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    file_id = uploader.upload_csv(tmp, "asp_normalized.csv", date_str, top_folder="raw")
    os.unlink(tmp)
    logger.info(f"asp_normalized.csv → raw/{date_str}/ ({len(df)}行) ({file_id})")
    return len(df)


def main():
    from phase1.drive_uploader import DriveUploader
    from phase1.date_range import parse_date_range, date_list

    start, end = parse_date_range(sys.argv[1:])
    logger.info(f"ASP正規化出力 期間: {start}〜{end}")

    uploader = DriveUploader()
    for d in date_list(start, end):
        export_for_date(uploader, d.isoformat())


if __name__ == "__main__":
    main()
