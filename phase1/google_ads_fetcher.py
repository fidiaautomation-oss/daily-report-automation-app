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
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def jst_yesterday() -> str:
    """日本時間基準の前日（YYYY-MM-DD）。

    GitHub Actionsランナーは UTC のため、JSTで計算しないと
    Google Ads Scripts が書き出す日付と1日ずれる。
    """
    return (datetime.now(JST) - timedelta(days=1)).date().isoformat()

import pandas as pd
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 各MCCが google_ads_<MCC ID> タブに書き出す。前方一致で全タブを読む。
SHEET_NAME_PREFIX = "google_ads"
OUTPUT_COLUMNS = [
    "date", "account_id", "account_name",
    "campaign_id", "campaign_name", "adgroup_id", "adgroup_name",
    "impressions", "clicks", "cost", "conversions",
]
# 重複判定キー（同一アカウントが複数MCCに紐づく場合の重複を除去）
DEDUPE_KEYS = ["date", "account_id", "campaign_id", "adgroup_id"]


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

    def _list_google_tabs(self) -> list:
        """google_ads で始まる全タブ名を返す。"""
        meta = self.service.spreadsheets().get(
            spreadsheetId=self.sheet_id, fields="sheets.properties(title)"
        ).execute()
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
        return [t for t in titles if t.startswith(SHEET_NAME_PREFIX)]

    def _read_tab(self, tab: str) -> pd.DataFrame:
        res = self.service.spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range=f"'{tab}'!A:K"
        ).execute()
        values = res.get("values", [])
        if len(values) < 2:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)
        header, *data = values
        df = pd.DataFrame(data, columns=header)
        for col in OUTPUT_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[OUTPUT_COLUMNS].astype(str)

    def fetch(self, target_date: str = None) -> pd.DataFrame:
        """全MCCタブ(google_ads_*)を結合し重複削除してDataFrameで返す。

        target_date 指定時はその日付のみに絞る。未指定（None）の場合は
        シートの全行を返す（スクリプトは前日1日分のみ出力するため、
        タイムゾーン計算に依存せずシートの内容をそのまま採用する）。
        """
        if not self.sheet_id:
            logger.warning("GOOGLE_ADS_SHEET_ID 未設定のためGoogle広告取得をスキップ")
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        tabs = self._list_google_tabs()
        if not tabs:
            logger.warning("google_ads_* タブが見つかりません")
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        frames = []
        for tab in tabs:
            tdf = self._read_tab(tab)
            logger.info(f"  タブ {tab}: {len(tdf)}行")
            if len(tdf):
                frames.append(tdf)
        if not frames:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        df = pd.concat(frames, ignore_index=True)
        before = len(df)
        # 重複削除（同一アカウントが複数MCCに紐づく場合）
        df = df.drop_duplicates(subset=DEDUPE_KEYS, keep="first").reset_index(drop=True)
        removed = before - len(df)
        if target_date:
            df = df[df["date"].str.strip() == target_date]
        dates = sorted(df["date"].str.strip().unique()) if len(df) else []
        logger.info(
            f"Google広告 取得: {len(df)}行（{len(tabs)}タブ結合・重複削除{removed}件）/ 日付={dates}"
        )
        return df

    def fetch_to_csv(self, output_path: str, target_date: str = None) -> str:
        """シートを取得しCSV保存。保存したデータの日付（YYYY-MM-DD）を返す。"""
        df = self.fetch(target_date)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        # データに含まれる日付を採用（複数あれば最新）。空なら target_date / JST前日
        if len(df) and df["date"].str.strip().any():
            return sorted(df["date"].str.strip().unique())[-1]
        return target_date or jst_yesterday()


def main():
    from phase1.drive_uploader import DriveUploader
    import tempfile

    # 引数があればその日付に絞る。無ければシートの内容をそのまま使う。
    target_date = sys.argv[1] if len(sys.argv) > 1 else None

    fetcher = GoogleAdsFetcher()
    uploader = DriveUploader()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp_path = f.name

    data_date = fetcher.fetch_to_csv(tmp_path, target_date)
    file_id = uploader.upload_csv(tmp_path, "google_ads.csv", data_date, top_folder="raw")
    os.unlink(tmp_path)
    print(f"google_ads.csv アップロード完了: raw/{data_date}/ ({file_id})")


if __name__ == "__main__":
    main()
