"""Google広告フェッチャー。

Google Ads Scripts が出力したスプレッドシート（google_ads シート）を読み込み、
前日分のデータを raw/YYYY-MM-DD/google_ads.csv として Drive に保存する。
取得項目は Yahoo広告フェッチャーと統一。

実行:
    python -m phase1.google_ads_fetcher            # 昨日分
    python -m phase1.google_ads_fetcher 2026-06-11 # 日付指定
"""

import json
import os
import sys
import logging
from datetime import date, timedelta

import pandas as pd
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SHEET_NAME = "google_ads"
OUTPUT_COLUMNS = [
    "date", "account_id", "account_name",
    "campaign_id", "campaign_name", "adgroup_id", "adgroup_name",
    "impressions", "clicks", "cost", "conversions",
]


class GoogleAdsFetcher:
    def __init__(self, sheet_id: str = None):
        self.sheet_id = sheet_id if sheet_id is not None else os.environ.get(
            "GOOGLE_ADS_SHEET_ID", ""
        )
        self._service = None

    def _load_credentials(self) -> Credentials:
        token_json = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON")
        if token_json:
            info = json.loads(token_json)
        else:
            token_path = os.environ.get("GOOGLE_TOKEN_PATH", "credentials/token.json")
            with open(token_path) as f:
                info = json.load(f)
        creds = Credentials(
            token=info.get("token"),
            refresh_token=info.get("refresh_token"),
            token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=info.get("client_id"),
            client_secret=info.get("client_secret"),
            scopes=info.get("scopes"),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    @property
    def service(self):
        if self._service is None:
            self._service = build("sheets", "v4", credentials=self._load_credentials())
        return self._service

    def fetch(self, target_date: str) -> pd.DataFrame:
        """出力シートを読み込み、対象日のデータをDataFrameで返す。"""
        if not self.sheet_id:
            logger.warning("GOOGLE_ADS_SHEET_ID 未設定のためGoogle広告取得をスキップ")
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        res = self.service.spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range=f"'{SHEET_NAME}'!A:K"
        ).execute()
        values = res.get("values", [])
        if len(values) < 2:
            logger.warning("google_ads シートにデータがありません")
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        header, *data = values
        df = pd.DataFrame(data, columns=header)
        # 想定列のみ・順序を統一（不足列は空で補完）
        for col in OUTPUT_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[OUTPUT_COLUMNS].astype(str)
        # 対象日のみに絞る（スクリプトは前日のみ出力するが保険）
        df = df[df["date"].str.strip() == target_date]
        logger.info(f"Google広告 {target_date}: {len(df)}行")
        return df

    def fetch_to_csv(self, output_path: str, target_date: str) -> None:
        df = self.fetch(target_date)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")


def main():
    from phase1.drive_uploader import DriveUploader
    import tempfile

    target_date = sys.argv[1] if len(sys.argv) > 1 else (
        date.today() - timedelta(days=1)
    ).isoformat()

    fetcher = GoogleAdsFetcher()
    uploader = DriveUploader()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp_path = f.name

    fetcher.fetch_to_csv(tmp_path, target_date)
    file_id = uploader.upload_csv(tmp_path, "google_ads.csv", target_date, top_folder="raw")
    os.unlink(tmp_path)
    print(f"google_ads.csv アップロード完了: {file_id}")


if __name__ == "__main__":
    main()
