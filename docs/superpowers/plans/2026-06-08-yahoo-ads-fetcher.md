# Yahoo広告フェッチャー Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yahoo検索広告API(v14)から昨日分の広告グループ単位パフォーマンスデータを取得し、`raw/YYYY-MM-DD/yahoo_ads.csv` としてGoogle Driveへ保存する。

**Architecture:** `YahooAdsFetcher` クラスがOAuth2リフレッシュトークンでアクセストークンを取得し、各アカウントについて「レポート定義作成 → ポーリング → TSVダウンロード → DataFrame化」を行い、全アカウントを結合してCSV出力する。外部HTTPは全て `requests` 経由のため、テストは `requests` をモックして検証する。

**Tech Stack:** Python 3.11+, requests, pandas, pytest, pytest-mock

---

## File Structure

- `phase1/yahoo_ads_fetcher.py` — 全面書き換え（`YahooAdsFetcher` クラス + `main()`）
- `tests/test_yahoo_ads_fetcher.py` — 新規（モックベースのユニットテスト）
- `.env.example` — Yahoo用環境変数を4つに刷新

---

## Task 1: 環境変数の刷新

**Files:**
- Modify: `.env.example`（Yahoo広告APIセクション）

- [ ] **Step 1: `.env.example` のYahooセクションを書き換える**

`.env.example` の以下の2行を:

```
# Yahoo広告API
YAHOO_ADS_ACCESS_TOKEN=your_access_token_here
YAHOO_ADS_ACCOUNT_IDS=1234567890,9876543210
```

次の内容に置き換える:

```
# Yahoo広告API（OAuth2）
YAHOO_ADS_CLIENT_ID=your_client_id_here
YAHOO_ADS_CLIENT_SECRET=your_client_secret_here
YAHOO_ADS_REFRESH_TOKEN=your_refresh_token_here
YAHOO_ADS_ACCOUNT_IDS=1234567890,9876543210
```

- [ ] **Step 2: コミット**

```bash
git add .env.example
git commit -m "chore: Yahoo広告APIをOAuth2環境変数へ刷新"
```

---

## Task 2: アクセストークン取得

**Files:**
- Modify: `phase1/yahoo_ads_fetcher.py`
- Test: `tests/test_yahoo_ads_fetcher.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_yahoo_ads_fetcher.py` を新規作成:

```python
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("YAHOO_ADS_CLIENT_ID", "cid")
    monkeypatch.setenv("YAHOO_ADS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YAHOO_ADS_REFRESH_TOKEN", "rtoken")
    monkeypatch.setenv("YAHOO_ADS_ACCOUNT_IDS", "111,222")


def test_get_access_token(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    mock_res = MagicMock()
    mock_res.json.return_value = {"access_token": "abc123", "expires_in": 3600}
    mock_res.raise_for_status.return_value = None

    with patch("phase1.yahoo_ads_fetcher.requests.post", return_value=mock_res) as mp:
        token = fetcher._get_access_token()

    assert token == "abc123"
    args, kwargs = mp.call_args
    assert "biz-oauth.yahoo.co.jp" in args[0]
    assert kwargs["data"]["grant_type"] == "refresh_token"
    assert kwargs["data"]["refresh_token"] == "rtoken"
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py::test_get_access_token -v`
Expected: FAIL（`ImportError` または `AttributeError`）

- [ ] **Step 3: 最小実装を書く**

`phase1/yahoo_ads_fetcher.py` を以下で全置換（後続タスクで追記していく土台）:

```python
import os
import time
import io
from datetime import date, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://biz-oauth.yahoo.co.jp/oauth2/v1/token"
API_BASE = "https://ads-search.yahooapis.jp/api/v14/ReportDefinitionService"

REPORT_FIELDS = [
    "DAY",
    "CAMPAIGN_NAME",
    "ADGROUP_NAME",
    "IMPRESSIONS",
    "CLICKS",
    "COST",
    "ALL_CONV",
]

# Yahooフィールド名 → 出力列名
FIELD_MAP = {
    "DAY": "date",
    "CAMPAIGN_NAME": "campaign_name",
    "ADGROUP_NAME": "adgroup_name",
    "IMPRESSIONS": "impressions",
    "CLICKS": "clicks",
    "COST": "cost",
    "ALL_CONV": "conversions",
}


class YahooAdsFetcher:
    POLL_INTERVAL_SEC = 10
    POLL_TIMEOUT_SEC = 600

    def __init__(self):
        self.client_id = os.environ["YAHOO_ADS_CLIENT_ID"]
        self.client_secret = os.environ["YAHOO_ADS_CLIENT_SECRET"]
        self.refresh_token = os.environ["YAHOO_ADS_REFRESH_TOKEN"]
        self.account_ids = os.environ["YAHOO_ADS_ACCOUNT_IDS"].split(",")
        self._access_token = None

    def _get_access_token(self) -> str:
        res = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
        )
        res.raise_for_status()
        return res.json()["access_token"]
```

- [ ] **Step 4: テスト合格を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py::test_get_access_token -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add phase1/yahoo_ads_fetcher.py tests/test_yahoo_ads_fetcher.py
git commit -m "feat: Yahoo広告アクセストークン取得を実装"
```

---

## Task 3: レポート定義作成

**Files:**
- Modify: `phase1/yahoo_ads_fetcher.py`
- Test: `tests/test_yahoo_ads_fetcher.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_yahoo_ads_fetcher.py` に追記:

```python
def test_create_report(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    fetcher._access_token = "tok"
    mock_res = MagicMock()
    mock_res.json.return_value = {
        "rval": {"values": [{"reportDefinition": {"reportJobId": 999}}]}
    }
    mock_res.raise_for_status.return_value = None

    with patch("phase1.yahoo_ads_fetcher.requests.post", return_value=mock_res) as mp:
        job_id = fetcher._create_report("111")

    assert job_id == 999
    args, kwargs = mp.call_args
    assert args[0].endswith("/add")
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    body = kwargs["json"]
    assert body["accountId"] == "111"
    op = body["operand"][0]
    assert op["reportType"] == "ADGROUP"
    assert op["dateRangeType"] == "CUSTOM_DATE"
    assert set(op["fields"]) == set(
        ["DAY", "CAMPAIGN_NAME", "ADGROUP_NAME", "IMPRESSIONS", "CLICKS", "COST", "ALL_CONV"]
    )
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py::test_create_report -v`
Expected: FAIL（`AttributeError: _create_report`）

- [ ] **Step 3: 最小実装を書く**

`YahooAdsFetcher` クラスに追記:

```python
    def _report_date(self) -> date:
        return date.today() - timedelta(days=1)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _create_report(self, account_id: str) -> int:
        report_date = self._report_date().strftime("%Y%m%d")
        body = {
            "accountId": account_id,
            "operand": [
                {
                    "reportName": f"daily_{account_id}_{report_date}",
                    "reportType": "ADGROUP",
                    "reportDateRangeType": "CUSTOM_DATE",
                    "dateRangeType": "CUSTOM_DATE",
                    "dateRange": {
                        "startDate": report_date,
                        "endDate": report_date,
                    },
                    "fields": REPORT_FIELDS,
                    "format": "TSV",
                    "encode": "UTF-8",
                }
            ],
        }
        res = requests.post(f"{API_BASE}/add", headers=self._headers(), json=body)
        res.raise_for_status()
        return res.json()["rval"]["values"][0]["reportDefinition"]["reportJobId"]
```

- [ ] **Step 4: テスト合格を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py::test_create_report -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add phase1/yahoo_ads_fetcher.py tests/test_yahoo_ads_fetcher.py
git commit -m "feat: Yahoo広告レポート定義作成を実装"
```

---

## Task 4: ステータスポーリング

**Files:**
- Modify: `phase1/yahoo_ads_fetcher.py`
- Test: `tests/test_yahoo_ads_fetcher.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_yahoo_ads_fetcher.py` に追記:

```python
def test_poll_report_completes(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    fetcher._access_token = "tok"

    def make_res(status):
        r = MagicMock()
        r.json.return_value = {
            "rval": {"values": [{"reportDefinition": {"reportJobStatus": status}}]}
        }
        r.raise_for_status.return_value = None
        return r

    responses = [make_res("WAIT"), make_res("COMPLETED")]
    with patch("phase1.yahoo_ads_fetcher.requests.post", side_effect=responses), \
         patch("phase1.yahoo_ads_fetcher.time.sleep"):
        ok = fetcher._poll_report("111", 999)

    assert ok is True


def test_poll_report_failed(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    fetcher._access_token = "tok"
    r = MagicMock()
    r.json.return_value = {
        "rval": {"values": [{"reportDefinition": {"reportJobStatus": "FAILED"}}]}
    }
    r.raise_for_status.return_value = None

    with patch("phase1.yahoo_ads_fetcher.requests.post", return_value=r), \
         patch("phase1.yahoo_ads_fetcher.time.sleep"):
        ok = fetcher._poll_report("111", 999)

    assert ok is False
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py -k poll -v`
Expected: FAIL（`AttributeError: _poll_report`）

- [ ] **Step 3: 最小実装を書く**

`YahooAdsFetcher` クラスに追記:

```python
    def _poll_report(self, account_id: str, job_id: int) -> bool:
        body = {
            "accountId": account_id,
            "reportJobIds": [job_id],
        }
        elapsed = 0
        while elapsed <= self.POLL_TIMEOUT_SEC:
            res = requests.post(f"{API_BASE}/get", headers=self._headers(), json=body)
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
```

- [ ] **Step 4: テスト合格を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py -k poll -v`
Expected: PASS（2件）

- [ ] **Step 5: コミット**

```bash
git add phase1/yahoo_ads_fetcher.py tests/test_yahoo_ads_fetcher.py
git commit -m "feat: Yahoo広告レポートのステータスポーリングを実装"
```

---

## Task 5: レポートダウンロード → DataFrame

**Files:**
- Modify: `phase1/yahoo_ads_fetcher.py`
- Test: `tests/test_yahoo_ads_fetcher.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_yahoo_ads_fetcher.py` に追記:

```python
def test_download_report(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    fetcher._access_token = "tok"

    tsv = (
        "DAY\tCAMPAIGN_NAME\tADGROUP_NAME\tIMPRESSIONS\tCLICKS\tCOST\tALL_CONV\n"
        "2026-06-07\tキャンペA\tグループX\t100\t5\t1200\t2\n"
    )
    r = MagicMock()
    r.text = tsv
    r.content = tsv.encode("utf-8")
    r.raise_for_status.return_value = None

    with patch("phase1.yahoo_ads_fetcher.requests.get", return_value=r):
        df = fetcher._download_report("111", 999)

    assert list(df.columns) == [
        "date", "campaign_name", "adgroup_name",
        "impressions", "clicks", "cost", "conversions", "account_id",
    ]
    assert len(df) == 1
    assert df.iloc[0]["campaign_name"] == "キャンペA"
    assert df.iloc[0]["account_id"] == "111"
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py::test_download_report -v`
Expected: FAIL（`AttributeError: _download_report`）

- [ ] **Step 3: 最小実装を書く**

`YahooAdsFetcher` クラスに追記:

```python
    def _download_report(self, account_id: str, job_id: int) -> pd.DataFrame:
        params = {"accountId": account_id, "reportJobId": job_id}
        res = requests.get(
            f"{API_BASE}/download", headers=self._headers(), params=params
        )
        res.raise_for_status()
        df = pd.read_csv(io.StringIO(res.text), sep="\t", dtype=str)
        # Yahooフィールド名 → 出力列名へリネーム（存在する列のみ）
        df = df.rename(columns={k: v for k, v in FIELD_MAP.items() if k in df.columns})
        keep = [v for v in FIELD_MAP.values() if v in df.columns]
        df = df[keep].copy()
        df["account_id"] = account_id
        return df
```

- [ ] **Step 4: テスト合格を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py::test_download_report -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add phase1/yahoo_ads_fetcher.py tests/test_yahoo_ads_fetcher.py
git commit -m "feat: Yahoo広告レポートのダウンロード・DataFrame化を実装"
```

---

## Task 6: 全アカウント統合 fetch_to_csv

**Files:**
- Modify: `phase1/yahoo_ads_fetcher.py`
- Test: `tests/test_yahoo_ads_fetcher.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_yahoo_ads_fetcher.py` に追記:

```python
def test_fetch_to_csv_combines_accounts(env, tmp_path):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()

    def fake_df(account_id, job_id):
        return pd.DataFrame([{
            "date": "2026-06-07", "campaign_name": "C", "adgroup_name": "G",
            "impressions": "10", "clicks": "1", "cost": "100",
            "conversions": "0", "account_id": account_id,
        }])

    with patch.object(fetcher, "_get_access_token", return_value="tok"), \
         patch.object(fetcher, "_create_report", return_value=999), \
         patch.object(fetcher, "_poll_report", return_value=True), \
         patch.object(fetcher, "_download_report", side_effect=fake_df):
        out = tmp_path / "yahoo_ads.csv"
        fetcher.fetch_to_csv(str(out))

    df = pd.read_csv(out, dtype=str)
    assert len(df) == 2
    assert set(df["account_id"]) == {"111", "222"}


def test_fetch_to_csv_skips_failed_account(env, tmp_path):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()

    def fake_df(account_id, job_id):
        return pd.DataFrame([{
            "date": "2026-06-07", "campaign_name": "C", "adgroup_name": "G",
            "impressions": "10", "clicks": "1", "cost": "100",
            "conversions": "0", "account_id": account_id,
        }])

    # 111は成功、222はポーリング失敗
    poll_results = {"111": True, "222": False}

    with patch.object(fetcher, "_get_access_token", return_value="tok"), \
         patch.object(fetcher, "_create_report", return_value=999), \
         patch.object(fetcher, "_poll_report", side_effect=lambda aid, jid: poll_results[aid]), \
         patch.object(fetcher, "_download_report", side_effect=fake_df):
        out = tmp_path / "yahoo_ads.csv"
        fetcher.fetch_to_csv(str(out))

    df = pd.read_csv(out, dtype=str)
    assert len(df) == 1
    assert set(df["account_id"]) == {"111"}


def test_fetch_to_csv_all_failed_writes_empty(env, tmp_path):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    with patch.object(fetcher, "_get_access_token", return_value="tok"), \
         patch.object(fetcher, "_create_report", return_value=999), \
         patch.object(fetcher, "_poll_report", return_value=False), \
         patch.object(fetcher, "_download_report", return_value=pd.DataFrame()):
        out = tmp_path / "yahoo_ads.csv"
        fetcher.fetch_to_csv(str(out))

    df = pd.read_csv(out, dtype=str)
    assert len(df) == 0
    assert list(df.columns) == [
        "date", "campaign_name", "adgroup_name",
        "impressions", "clicks", "cost", "conversions", "account_id",
    ]
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py -k fetch_to_csv -v`
Expected: FAIL（`AttributeError: fetch_to_csv`）

- [ ] **Step 3: 最小実装を書く**

`YahooAdsFetcher` クラスに追記:

```python
    OUTPUT_COLUMNS = [
        "date", "campaign_name", "adgroup_name",
        "impressions", "clicks", "cost", "conversions", "account_id",
    ]

    def _fetch_account(self, account_id: str) -> pd.DataFrame:
        job_id = self._create_report(account_id)
        if not self._poll_report(account_id, job_id):
            print(f"[WARN] Yahoo広告 アカウント {account_id} のレポート取得に失敗・スキップ")
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        return self._download_report(account_id, job_id)

    def fetch_to_csv(self, output_path: str) -> None:
        self._access_token = self._get_access_token()
        dfs = []
        for aid in self.account_ids:
            df = self._fetch_account(aid)
            if not df.empty:
                dfs.append(df)
        if dfs:
            result = pd.concat(dfs, ignore_index=True)
        else:
            result = pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        result.to_csv(output_path, index=False, encoding="utf-8-sig")
```

- [ ] **Step 4: テスト合格を確認**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py -k fetch_to_csv -v`
Expected: PASS（3件）

- [ ] **Step 5: コミット**

```bash
git add phase1/yahoo_ads_fetcher.py tests/test_yahoo_ads_fetcher.py
git commit -m "feat: Yahoo広告 全アカウント統合CSV出力を実装"
```

---

## Task 7: main() の更新と全テスト確認

**Files:**
- Modify: `phase1/yahoo_ads_fetcher.py`（末尾の `main()`）

- [ ] **Step 1: `main()` を追記**

`phase1/yahoo_ads_fetcher.py` の末尾に追記:

```python
def main():
    from phase1.drive_uploader import DriveUploader
    import tempfile

    date_str = (date.today() - timedelta(days=1)).isoformat()
    fetcher = YahooAdsFetcher()
    uploader = DriveUploader()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp_path = f.name

    fetcher.fetch_to_csv(tmp_path)
    file_id = uploader.upload_csv(tmp_path, "yahoo_ads.csv", date_str)
    print(f"yahoo_ads.csv アップロード完了: {file_id}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 全テストを実行**

Run: `cd /Users/mitomi/Claude/daily-report-automation && python -m pytest tests/test_yahoo_ads_fetcher.py -v`
Expected: PASS（全8件）

- [ ] **Step 3: コミット**

```bash
git add phase1/yahoo_ads_fetcher.py
git commit -m "feat: Yahoo広告 main()をdrive_uploader連携・昨日日付に更新"
```

---

## 注意事項（実装者向け）

- `drive_uploader.py` の `upload_csv(local_path, filename, date_str)` シグネチャは既存ASPダウンローダーと同じものを利用する。実装前に `phase1/drive_uploader.py` を読んで引数順を確認すること。
- Yahoo APIのレスポンス構造（`rval.values[0].reportDefinition`）はv14ドキュメント準拠。実APIで `KeyError` が出た場合は、レスポンスをログ出力して構造を確認し、`_create_report` / `_poll_report` のパスを実体に合わせて微修正する。
- 実際のAPI疎通テストは認証情報を `.env` に設定後、`python -m phase1.yahoo_ads_fetcher` で実行して `date` 列が昨日のみであることを確認する。
