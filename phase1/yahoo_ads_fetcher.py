import os
import sys
import time
import io
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://biz-oauth.yahoo.co.jp/oauth/v1/token"
API_VERSION = "v17"
API_BASE = f"https://ads-search.yahooapis.jp/api/{API_VERSION}/ReportDefinitionService"
BASE_ACCOUNT_API = f"https://ads-search.yahooapis.jp/api/{API_VERSION}/BaseAccountService"

REPORT_FIELDS = [
    "DAY",
    "CAMPAIGN_ID",
    "CAMPAIGN_NAME",
    "ADGROUP_ID",
    "ADGROUP_NAME",
    "IMPS",
    "CLICKS",
    "COST",
    "ALL_CONV",
]

# Yahooフィールド名 → 出力列名
FIELD_MAP = {
    "DAY": "date",
    "CAMPAIGN_ID": "campaign_id",
    "CAMPAIGN_NAME": "campaign_name",
    "ADGROUP_ID": "adgroup_id",
    "ADGROUP_NAME": "adgroup_name",
    "IMPS": "impressions",
    "CLICKS": "clicks",
    "COST": "cost",
    "ALL_CONV": "conversions",
}


class YahooAdsFetcher:
    POLL_INTERVAL_SEC = 10
    POLL_TIMEOUT_SEC = 600
    ACCOUNT_PAGE_SIZE = 200  # BaseAccountService の numberResults 上限

    OUTPUT_COLUMNS = [
        "date", "account_id", "account_name",
        "campaign_id", "campaign_name", "adgroup_id", "adgroup_name",
        "impressions", "clicks", "cost", "conversions",
    ]

    def __init__(self):
        self.client_id = os.environ["YAHOO_ADS_CLIENT_ID"]
        self.client_secret = os.environ["YAHOO_ADS_CLIENT_SECRET"]
        # ビジネスIDごとのリフレッシュトークン（1トークン＝多数アカウントにアクセス可）
        self.refresh_tokens = [
            t.strip()
            for t in os.environ["YAHOO_ADS_REFRESH_TOKENS"].split(",")
            if t.strip()
        ]
        if not self.refresh_tokens:
            raise ValueError("YAHOO_ADS_REFRESH_TOKENS が設定されていません")
        self._access_token = None

    # ── 認証 ────────────────────────────────────────────────
    def _get_access_token(self, refresh_token: str) -> str:
        res = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
            },
        )
        res.raise_for_status()
        return res.json()["access_token"]

    def _report_date(self) -> date:
        # 日本時間基準の前日（GitHub ActionsランナーはUTCのため）
        return (datetime.now(JST) - timedelta(days=1)).date()

    def _headers(self, account_id) -> dict:
        # ReportDefinitionService は x-z-base-account-id ヘッダーが必須
        return {
            "Authorization": f"Bearer {self._access_token}",
            "x-z-base-account-id": str(account_id),
            "Content-Type": "application/json",
        }

    def _bootstrap_headers(self) -> dict:
        # BaseAccountService は x-z-base-account-id 不要（アカウント発見の起点）
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    # ── アカウント自動発見 ──────────────────────────────────
    def _discover_accounts_for_token(self, refresh_token: str) -> list:
        """1つのリフレッシュトークンでアクセス可能な通常広告アカウントを列挙する。

        MCC（管理）アカウントはレポート対象外のため除外する。
        戻り値: [{"account_id": str, "account_name": str}, ...]
        """
        self._access_token = self._get_access_token(refresh_token)
        accounts = []
        start_index = 1
        while True:
            res = requests.post(
                f"{BASE_ACCOUNT_API}/get",
                headers=self._bootstrap_headers(),
                json={"numberResults": self.ACCOUNT_PAGE_SIZE, "startIndex": start_index},
            )
            res.raise_for_status()
            rval = res.json().get("rval", {})
            values = rval.get("values") or []
            for v in values:
                acc = v.get("account", {})
                if str(acc.get("isMccAccount", "FALSE")).upper() == "TRUE":
                    continue
                accounts.append(
                    {
                        "account_id": str(acc.get("accountId")),
                        "account_name": acc.get("accountName", ""),
                    }
                )
            total = rval.get("totalNumEntries", 0)
            if start_index + self.ACCOUNT_PAGE_SIZE > total or not values:
                break
            start_index += self.ACCOUNT_PAGE_SIZE
        return accounts

    def discover_accounts(self) -> list:
        """全リフレッシュトークンを横断してアクセス可能な通常広告アカウントを発見する。

        同一アカウントが複数トークンから見える場合は最初に見つけたものを採用（重複排除）。
        戻り値: [{"account_id": str, "account_name": str, "refresh_token": str}, ...]
        """
        discovered = []
        seen = set()
        for rt in self.refresh_tokens:
            for acc in self._discover_accounts_for_token(rt):
                aid = acc["account_id"]
                if aid in seen:
                    continue
                seen.add(aid)
                discovered.append({**acc, "refresh_token": rt})
        return discovered

    # ── レポート取得 ────────────────────────────────────────
    def _create_report(self, account_id) -> int:
        report_date = self._report_date().strftime("%Y%m%d")
        account_id = int(account_id)
        body = {
            "accountId": account_id,
            "operand": [
                {
                    "reportName": f"daily_{account_id}_{report_date}",
                    "reportType": "ADGROUP",
                    "reportDateRangeType": "CUSTOM_DATE",
                    "dateRange": {
                        "startDate": report_date,
                        "endDate": report_date,
                    },
                    "fields": REPORT_FIELDS,
                    "reportDownloadFormat": "TSV",
                    "reportDownloadEncode": "UTF8",
                }
            ],
        }
        res = requests.post(
            f"{API_BASE}/add", headers=self._headers(account_id), json=body
        )
        res.raise_for_status()
        return res.json()["rval"]["values"][0]["reportDefinition"]["reportJobId"]

    def _poll_report(self, account_id, job_id: int) -> bool:
        body = {
            "accountId": int(account_id),
            "reportJobIds": [job_id],
        }
        elapsed = 0
        while elapsed <= self.POLL_TIMEOUT_SEC:
            res = requests.post(
                f"{API_BASE}/get", headers=self._headers(account_id), json=body
            )
            res.raise_for_status()
            status = (
                res.json()["rval"]["values"][0]["reportDefinition"]["reportJobStatus"]
            )
            if status == "COMPLETED":
                return True
            if status == "FAILED":
                return False
            time.sleep(self.POLL_INTERVAL_SEC)
            elapsed += self.POLL_INTERVAL_SEC
        return False

    def _download_report(self, account_id, job_id: int, account_name: str = "") -> pd.DataFrame:
        body = {"accountId": int(account_id), "reportJobId": job_id}
        res = requests.post(
            f"{API_BASE}/download", headers=self._headers(account_id), json=body
        )
        res.raise_for_status()
        df = pd.read_csv(io.StringIO(res.text), sep="\t", dtype=str)
        # ダウンロードCSVのヘッダーは日本語。列順はリクエストの fields 順と一致するため、
        # 位置でリクエストフィールド → 出力列名へマッピングする。
        expected = [FIELD_MAP[f] for f in REPORT_FIELDS]
        if len(df.columns) == len(expected):
            df.columns = expected
        else:
            # 想定外の列構成（合計行など）。一致する列だけ残す
            df = df.rename(columns={k: v for k, v in FIELD_MAP.items() if k in df.columns})
            df = df[[c for c in expected if c in df.columns]].copy()
        # 実績ゼロのアカウントは日付空の合計行のみ返るため除去する
        if "date" in df.columns:
            df = df[df["date"].notna() & (df["date"].astype(str).str.strip() != "")]
        df = df.copy()
        df["account_id"] = str(account_id)
        df["account_name"] = account_name
        return df

    def _fetch_account(self, account_id, refresh_token: str, account_name: str = "") -> pd.DataFrame:
        # アカウントが属するビジネスIDのトークンでアクセストークンを取得
        self._access_token = self._get_access_token(refresh_token)
        job_id = self._create_report(account_id)
        if not self._poll_report(account_id, job_id):
            print(f"[WARN] Yahoo広告 アカウント {account_id} のレポート取得に失敗・スキップ")
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        return self._download_report(account_id, job_id, account_name)

    def fetch_to_csv(self, output_path: str) -> None:
        accounts = self.discover_accounts()
        print(f"[INFO] Yahoo広告 対象アカウント: {len(accounts)}件を自動発見")
        dfs = []
        for acc in accounts:
            df = self._fetch_account(
                acc["account_id"], acc["refresh_token"], acc["account_name"]
            )
            if not df.empty:
                dfs.append(df)
        if dfs:
            result = pd.concat(dfs, ignore_index=True)
            result = result[self.OUTPUT_COLUMNS]
        else:
            result = pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        result.to_csv(output_path, index=False, encoding="utf-8-sig")

    # ── .env への反映 ──────────────────────────────────────
    def write_accounts_to_env(self, env_path: str = ".env") -> list:
        """発見した全アカウントIDを .env の YAHOO_ADS_ACCOUNT_IDS に書き戻す（可視化用）。

        既存の YAHOO_ADS_ACCOUNT_IDS 行を置き換える。無ければ追記する。
        併せて、アカウントID→名称の対応をコメント行として書き出す。
        戻り値: 発見したアカウントのリスト。
        """
        accounts = self.discover_accounts()
        ids_csv = ",".join(a["account_id"] for a in accounts)

        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []

        # 既存の自動生成ブロック（マーカー間）と ACCOUNT_IDS 行を除去
        marker_start = "# === YAHOO_ADS_ACCOUNTS (auto-generated) ===\n"
        marker_end = "# === /YAHOO_ADS_ACCOUNTS ===\n"
        cleaned = []
        skipping = False
        for line in lines:
            if line == marker_start:
                skipping = True
                continue
            if line == marker_end:
                skipping = False
                continue
            if skipping:
                continue
            if line.startswith("YAHOO_ADS_ACCOUNT_IDS="):
                continue
            cleaned.append(line)

        if cleaned and not cleaned[-1].endswith("\n"):
            cleaned[-1] += "\n"

        block = [marker_start]
        block.append("# 下記は discover 実行時に自動取得したアカウント一覧（ID: 名称）\n")
        for a in accounts:
            block.append(f"#   {a['account_id']}: {a['account_name']}\n")
        block.append(f"YAHOO_ADS_ACCOUNT_IDS={ids_csv}\n")
        block.append(marker_end)

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(cleaned + block)

        print(f"[INFO] {env_path} に {len(accounts)}件のアカウントIDを反映しました")
        return accounts


def main():
    from phase1.drive_uploader import DriveUploader
    import tempfile

    date_str = (datetime.now(JST) - timedelta(days=1)).date().isoformat()
    fetcher = YahooAdsFetcher()
    uploader = DriveUploader()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp_path = f.name

    fetcher.fetch_to_csv(tmp_path)
    file_id = uploader.upload_csv(tmp_path, "yahoo_ads.csv", date_str)
    print(f"yahoo_ads.csv アップロード完了: {file_id}")


def discover():
    """アカウントIDを自動取得し .env に反映する（手動実行用）。"""
    fetcher = YahooAdsFetcher()
    accounts = fetcher.write_accounts_to_env()
    for a in accounts:
        print(f"  {a['account_id']}: {a['account_name']}")
    print(f"合計 {len(accounts)} アカウント")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "discover":
        discover()
    else:
        main()
