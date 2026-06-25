"""案件管理シートのマスタ（案件名・サイト・広告）をDrive最新データで更新する。

広告マスタには Yahoo / Google 両方の (配信プラットフォーム, 取得単位, 名称, ID) を反映する。
毎朝8〜9時（Google広告の取得後）にスケジュール実行する想定。
Drive読込 + Sheets書込のみのためIP制限を受けず、クラウド/ローカルどちらでも動く。

実行:
    python -m phase2.refresh_masters            # シートの取得日範囲の末尾 or 前日
    python -m phase2.refresh_masters 2026-06-22 # 日付指定
"""

import logging
import sys

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    from phase1.drive_uploader import DriveUploader
    from phase1.date_range import parse_date_range
    from phase2.personal_csv_builder import PersonalCsvBuilder
    from phase2.sheet_reader import SheetReader

    # 期間の末尾（最新日）のデータでマスタを更新する
    _, end = parse_date_range(sys.argv[1:])
    date_str = end.isoformat()
    logger.info(f"マスタ更新 対象日: {date_str}")

    uploader = DriveUploader()
    builder = PersonalCsvBuilder()
    reader = SheetReader()

    raw_files = uploader.download_folder_csvs(date_str, top_folder="raw")
    asp_df = builder.normalize_asp(raw_files)
    yahoo_df = builder.normalize_yahoo(raw_files)
    google_df = builder.normalize_google(raw_files)
    logger.info(
        f"ASP明細{len(asp_df)}行 / Yahoo{len(yahoo_df)}行 / Google{len(google_df)}行"
    )

    reader.update_masters(
        builder.extract_case_master(asp_df),
        builder.extract_site_master(asp_df),
        builder.extract_ad_master(yahoo_df, google_df),
    )
    reader.setup_input_helpers()
    logger.info("マスタ更新・入力支援の再設定が完了しました")


if __name__ == "__main__":
    main()
