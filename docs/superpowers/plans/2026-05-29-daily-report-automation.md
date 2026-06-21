# 日報自動化システム 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ASP・Google広告・Yahoo広告からデータを取得し、担当者別に既存日報ExcelへデータをフィットするPythonシステムをGitHub Actionsで毎朝自動実行する。

**Architecture:** Phase1（データ取得→Drive保存）→ Phase2（個人別CSV生成）→ Phase3（Excel書き込み）の3フェーズをGitHub ActionsのJobチェーンで順次実行する。各フェーズは独立したPythonモジュールとして分離し、単体テスト可能にする。

**Tech Stack:** Python 3.11+, Playwright, gspread, pandas, openpyxl, google-api-python-client, requests, pytest, GitHub Actions

---

## ファイル構成

| ファイル | 責務 |
|---------|------|
| `requirements.txt` | 依存パッケージ一覧 |
| `.env.example` | 環境変数のテンプレート |
| `config/asp_sites.yaml` | ASPサイトURL・ログイン設定 |
| `config/db_mapping.yaml` | 担当案件DB列マッピング定義 |
| `config/excel_mapping.yaml` | CSV→Excelセル対応表 |
| `phase1/asp_downloader.py` | PlaywrightでASP CSVダウンロード |
| `phase1/google_ads_fetcher.py` | gspreadでGoogle Ads Scriptsデータ取得 |
| `phase1/yahoo_ads_fetcher.py` | requests+pandasでYahoo広告API取得 |
| `phase1/drive_uploader.py` | Drive raw/YYYY-MM-DD/ へCSV保存 |
| `phase2/db_loader.py` | 担当案件DBスプレッドシートを読み込みDataFrame返却 |
| `phase2/personal_csv_builder.py` | raw CSVと担当案件DBをJOINして個人別CSV生成 |
| `phase3/excel_writer.py` | openpyxlでExcelテンプレートへ値書き込み |
| `phase3/report_archiver.py` | 完成ExcelをDrive report/ へ保存 |
| `.github/workflows/daily_report.yml` | GitHub Actions定義 |
| `tests/test_phase1.py` | Phase1ユニットテスト |
| `tests/test_phase2.py` | Phase2ユニットテスト |
| `tests/test_phase3.py` | Phase3ユニットテスト |

---

## Task 1: プロジェクト骨格とrequirements.txt

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`

- [ ] **Step 1: requirements.txt を作成する**

```
playwright==1.44.0
gspread==6.1.2
google-auth==2.29.0
google-api-python-client==2.128.0
pandas==2.2.2
openpyxl==3.1.2
requests==2.31.0
python-dotenv==1.0.1
pytest==8.2.0
pytest-mock==3.14.0
PyYAML==6.0.1
```

- [ ] **Step 2: .env.example を作成する**

```bash
# Google認証（サービスアカウントのJSONキーファイルパス）
GOOGLE_SERVICE_ACCOUNT_JSON=credentials/service_account.json

# Google Drive フォルダID
DRIVE_ROOT_FOLDER_ID=your_folder_id_here

# 担当案件DBスプレッドシートID
ASSIGNMENT_SPREADSHEET_ID=your_spreadsheet_id_here

# Google Ads ScriptsのスプレッドシートID
GOOGLE_ADS_SPREADSHEET_ID=your_spreadsheet_id_here

# Yahoo広告API
YAHOO_ADS_ACCESS_TOKEN=your_access_token_here
YAHOO_ADS_ACCOUNT_IDS=1234567890,9876543210

# ASP設定
ASP_A_URL=https://example-asp.com
ASP_A_USERNAME=your_username
ASP_A_PASSWORD=your_password
```

- [ ] **Step 3: .gitignore を作成する**

```
.env
credentials/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
```

- [ ] **Step 4: 依存パッケージをインストールする**

```bash
pip install -r requirements.txt
playwright install chromium
```

期待出力: `Successfully installed ...` が表示される

- [ ] **Step 5: コミットする**

```bash
git add requirements.txt .env.example .gitignore
git commit -m "feat: プロジェクト骨格を作成"
```

---

## Task 2: config ファイルを作成する

**Files:**
- Create: `config/asp_sites.yaml`
- Create: `config/db_mapping.yaml`
- Create: `config/excel_mapping.yaml`

- [ ] **Step 1: config/asp_sites.yaml を作成する**

```yaml
asp_sites:
  asp_A:
    name: "asp_A"
    url: "${ASP_A_URL}"
    username: "${ASP_A_USERNAME}"
    password: "${ASP_A_PASSWORD}"
    # ダウンロードしたCSVのファイル名パターン（globで使用）
    csv_filename_pattern: "report_*.csv"
    # CSVの日付列名
    date_column: "date"
```

- [ ] **Step 2: config/db_mapping.yaml を作成する**

```yaml
# 担当案件DBの各列名と、raw CSVの対応列名のマッピング
mappings:
  asp:
    # 担当案件DBの "案件ID" 列 → asp raw CSVの "item_id" 列でJOIN
    join_key_db: "案件ID"
    join_key_raw: "item_id"
  google:
    join_key_db: "媒体アカウントID"
    join_key_raw: "account_id"
  yahoo:
    join_key_db: "媒体アカウントID"
    join_key_raw: "advertiser_id"
```

- [ ] **Step 3: config/excel_mapping.yaml を作成する**

```yaml
sheet_name: "日報"
data_start_row: 5
mappings:
  - csv_col: "date"
    excel_col: "B"
  - csv_col: "campaign"
    excel_col: "C"
  - csv_col: "clicks"
    excel_col: "F"
  - csv_col: "cv_count"
    excel_col: "H"
  - csv_col: "cost"
    excel_col: "J"
  - csv_col: "cpa"
    excel_col: "K"
```

> **注意:** 実際の日報Excelを開いて列構成を確認し、このファイルを正確に設定してから Phase3 を実行すること。

- [ ] **Step 4: コミットする**

```bash
git add config/
git commit -m "feat: configファイルのテンプレートを追加"
```

---

## Task 3: Drive APIヘルパーを作成する（Phase1で共通使用）

**Files:**
- Create: `phase1/drive_uploader.py`
- Create: `tests/test_phase1.py`（Drive部分）

- [ ] **Step 1: テストを先に書く**

`tests/test_phase1.py` を作成:

```python
import pytest
from unittest.mock import MagicMock, patch
from phase1.drive_uploader import DriveUploader


def test_get_or_create_folder_returns_existing_id():
    """既存フォルダIDを返すこと"""
    uploader = DriveUploader.__new__(DriveUploader)
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {
        "files": [{"id": "existing_folder_id"}]
    }
    uploader.service = mock_service

    result = uploader._get_or_create_folder("raw", "parent_id")
    assert result == "existing_folder_id"


def test_get_or_create_folder_creates_new_when_missing():
    """フォルダが存在しない場合は作成すること"""
    uploader = DriveUploader.__new__(DriveUploader)
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {"files": []}
    mock_service.files().create().execute.return_value = {"id": "new_folder_id"}
    uploader.service = mock_service

    result = uploader._get_or_create_folder("2026-05-29", "parent_id")
    assert result == "new_folder_id"
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

```bash
pytest tests/test_phase1.py -v
```

期待出力: `ImportError` または `ModuleNotFoundError`（まだファイルがないため）

- [ ] **Step 3: DriveUploader を実装する**

`phase1/drive_uploader.py` を作成:

```python
import os
from datetime import date
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()


class DriveUploader:
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    def __init__(self):
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            scopes=self.SCOPES,
        )
        self.service = build("drive", "v3", credentials=creds)
        self.root_folder_id = os.environ["DRIVE_ROOT_FOLDER_ID"]

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
            f" and '{parent_id}' in parents and trashed=false"
        )
        res = self.service.files().list(q=query, fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self.service.files().create(body=meta, fields="id").execute()
        return folder["id"]

    def upload_csv(self, local_path: str, filename: str, date_str: str) -> str:
        """CSVファイルをDrive raw/YYYY-MM-DD/ へアップロードする。ファイルIDを返す。"""
        raw_folder_id = self._get_or_create_folder("raw", self.root_folder_id)
        date_folder_id = self._get_or_create_folder(date_str, raw_folder_id)

        media = MediaFileUpload(local_path, mimetype="text/csv")
        file_meta = {"name": filename, "parents": [date_folder_id]}
        uploaded = (
            self.service.files().create(body=file_meta, media_body=media, fields="id").execute()
        )
        return uploaded["id"]
```

- [ ] **Step 4: テストを実行してパスすることを確認する**

```bash
pytest tests/test_phase1.py -v
```

期待出力: `2 passed`

- [ ] **Step 5: コミットする**

```bash
git add phase1/drive_uploader.py tests/test_phase1.py
git commit -m "feat: DriveUploaderを実装"
```

---

## Task 4: ASP ダウンローダーを実装する（Playwright）

**Files:**
- Modify: `phase1/asp_downloader.py`（新規作成）
- Modify: `tests/test_phase1.py`（テスト追加）

- [ ] **Step 1: テストを追加する**

`tests/test_phase1.py` に追記:

```python
import tempfile
import csv
from phase1.asp_downloader import AspDownloader


def test_asp_downloader_returns_csv_path(tmp_path):
    """ダウンロード済みCSVのパスが返ること（Playwright部分はモック）"""
    downloader = AspDownloader.__new__(AspDownloader)
    downloader.download_dir = str(tmp_path)

    # ダミーCSVを作成（Playwrightが落としたとみなす）
    csv_path = tmp_path / "report_20260529.csv"
    csv_path.write_text("item_id,date,clicks\nA001,2026-05-29,100\n")

    result = downloader._find_downloaded_csv("report_*.csv")
    assert result == str(csv_path)
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

```bash
pytest tests/test_phase1.py::test_asp_downloader_returns_csv_path -v
```

期待出力: `ImportError`

- [ ] **Step 3: AspDownloader を実装する**

`phase1/asp_downloader.py` を作成:

```python
import os
import glob
import tempfile
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import yaml

load_dotenv()


class AspDownloader:
    def __init__(self, config_path: str = "config/asp_sites.yaml"):
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        self.sites = raw["asp_sites"]
        self.download_dir = tempfile.mkdtemp()

    def _find_downloaded_csv(self, pattern: str) -> str:
        """ダウンロードディレクトリからパターンに一致するCSVを返す"""
        matches = glob.glob(os.path.join(self.download_dir, pattern))
        if not matches:
            raise FileNotFoundError(f"CSVが見つかりません: {pattern} in {self.download_dir}")
        return sorted(matches)[-1]  # 最新のファイルを返す

    def download(self, asp_name: str) -> str:
        """指定ASPからCSVをダウンロードしてローカルパスを返す"""
        site = self.sites[asp_name]
        url = os.path.expandvars(site["url"])
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        pattern = site["csv_filename_pattern"]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            # ASPにログイン（サイトごとにカスタマイズが必要）
            page.goto(url)
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")

            # CSVダウンロードリンクをクリック
            with page.expect_download() as download_info:
                page.click('a:has-text("CSVダウンロード")')
            download = download_info.value
            dest = os.path.join(self.download_dir, download.suggested_filename)
            download.save_as(dest)
            browser.close()

        return self._find_downloaded_csv(pattern)


def main():
    from phase1.drive_uploader import DriveUploader
    from datetime import date

    date_str = date.today().isoformat()
    downloader = AspDownloader()
    uploader = DriveUploader()

    local_path = downloader.download("asp_A")
    file_id = uploader.upload_csv(local_path, "asp_A.csv", date_str)
    print(f"asp_A.csv アップロード完了: {file_id}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストを実行してパスすることを確認する**

```bash
pytest tests/test_phase1.py -v
```

期待出力: `3 passed`

- [ ] **Step 5: コミットする**

```bash
git add phase1/asp_downloader.py tests/test_phase1.py
git commit -m "feat: ASPダウンローダーを実装（Playwright）"
```

---

## Task 5: Google Ads フェッチャーを実装する

**Files:**
- Create: `phase1/google_ads_fetcher.py`
- Modify: `tests/test_phase1.py`（テスト追加）

- [ ] **Step 1: テストを追加する**

`tests/test_phase1.py` に追記:

```python
import pandas as pd
from phase1.google_ads_fetcher import GoogleAdsFetcher


def test_google_ads_fetcher_returns_dataframe(tmp_path):
    """gspreadから取得したデータがDataFrameになること"""
    fetcher = GoogleAdsFetcher.__new__(GoogleAdsFetcher)

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = [
        {"date": "2026-05-29", "account_id": "123-456", "clicks": 100, "cost": 5000},
    ]
    fetcher.worksheet = mock_ws

    df = fetcher._fetch_as_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert "clicks" in df.columns
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

```bash
pytest tests/test_phase1.py::test_google_ads_fetcher_returns_dataframe -v
```

期待出力: `ImportError`

- [ ] **Step 3: GoogleAdsFetcher を実装する**

`phase1/google_ads_fetcher.py` を作成:

```python
import os
import pandas as pd
import gspread
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()


class GoogleAdsFetcher:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    def __init__(self):
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            scopes=self.SCOPES,
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(os.environ["GOOGLE_ADS_SPREADSHEET_ID"])
        self.worksheet = spreadsheet.sheet1

    def _fetch_as_dataframe(self) -> pd.DataFrame:
        records = self.worksheet.get_all_records()
        return pd.DataFrame(records)

    def fetch_to_csv(self, output_path: str) -> None:
        """Google Ads Scriptsのスプレッドシートを読み込んでCSVへ書き出す"""
        df = self._fetch_as_dataframe()
        df.to_csv(output_path, index=False, encoding="utf-8-sig")


def main():
    from phase1.drive_uploader import DriveUploader
    from datetime import date
    import tempfile

    date_str = date.today().isoformat()
    fetcher = GoogleAdsFetcher()
    uploader = DriveUploader()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp_path = f.name

    fetcher.fetch_to_csv(tmp_path)
    file_id = uploader.upload_csv(tmp_path, "google_ads.csv", date_str)
    print(f"google_ads.csv アップロード完了: {file_id}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストを実行してパスすることを確認する**

```bash
pytest tests/test_phase1.py -v
```

期待出力: `4 passed`

- [ ] **Step 5: コミットする**

```bash
git add phase1/google_ads_fetcher.py tests/test_phase1.py
git commit -m "feat: Google Adsフェッチャーを実装"
```

---

## Task 6: Yahoo広告フェッチャーを実装する

**Files:**
- Create: `phase1/yahoo_ads_fetcher.py`
- Modify: `tests/test_phase1.py`（テスト追加）

- [ ] **Step 1: テストを追加する**

`tests/test_phase1.py` に追記:

```python
from phase1.yahoo_ads_fetcher import YahooAdsFetcher


def test_yahoo_ads_fetcher_returns_dataframe():
    """Yahoo広告APIのレスポンスをDataFrameに変換できること"""
    fetcher = YahooAdsFetcher.__new__(YahooAdsFetcher)
    fetcher.account_ids = ["1234567890"]
    fetcher.access_token = "dummy_token"

    mock_response = {
        "rval": {
            "values": [
                {
                    "campaignReport": {
                        "date": "20260529",
                        "advertiserID": "1234567890",
                        "clicks": 50,
                        "cost": 3000,
                    }
                }
            ]
        }
    }

    with patch("phase1.yahoo_ads_fetcher.requests.post") as mock_post:
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = MagicMock()
        df = fetcher._fetch_account("1234567890")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

```bash
pytest tests/test_phase1.py::test_yahoo_ads_fetcher_returns_dataframe -v
```

期待出力: `ImportError`

- [ ] **Step 3: YahooAdsFetcher を実装する**

`phase1/yahoo_ads_fetcher.py` を作成:

```python
import os
import pandas as pd
import requests
from datetime import date
from dotenv import load_dotenv

load_dotenv()

YAHOO_ADS_API_URL = "https://ads-search.yahooapis.jp/api/v14/ReportDefinitionService/download"


class YahooAdsFetcher:
    def __init__(self):
        self.access_token = os.environ["YAHOO_ADS_ACCESS_TOKEN"]
        self.account_ids = os.environ["YAHOO_ADS_ACCOUNT_IDS"].split(",")

    def _fetch_account(self, account_id: str) -> pd.DataFrame:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        payload = {
            "accountId": account_id,
            "dateRange": {"startDate": date.today().isoformat(), "endDate": date.today().isoformat()},
        }
        res = requests.post(YAHOO_ADS_API_URL, json=payload, headers=headers)
        res.raise_for_status()
        data = res.json()

        rows = []
        for item in data.get("rval", {}).get("values", []):
            report = item.get("campaignReport", {})
            rows.append({
                "date": report.get("date"),
                "advertiser_id": report.get("advertiserID"),
                "clicks": report.get("clicks"),
                "cost": report.get("cost"),
            })
        return pd.DataFrame(rows)

    def fetch_to_csv(self, output_path: str) -> None:
        """全アカウントのデータを取得して1つのCSVへ書き出す"""
        dfs = [self._fetch_account(aid) for aid in self.account_ids]
        df = pd.concat(dfs, ignore_index=True)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")


def main():
    from phase1.drive_uploader import DriveUploader
    from datetime import date
    import tempfile

    date_str = date.today().isoformat()
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

- [ ] **Step 4: テストを実行してパスすることを確認する**

```bash
pytest tests/test_phase1.py -v
```

期待出力: `5 passed`

- [ ] **Step 5: コミットする**

```bash
git add phase1/yahoo_ads_fetcher.py tests/test_phase1.py
git commit -m "feat: Yahoo広告フェッチャーを実装"
```

---

## Task 7: Phase2 担当案件DBローダーを実装する

**Files:**
- Create: `phase2/db_loader.py`
- Create: `tests/test_phase2.py`

- [ ] **Step 1: テストを作成する**

`tests/test_phase2.py` を作成:

```python
import pytest
import pandas as pd
from unittest.mock import MagicMock
from phase2.db_loader import DbLoader


def test_db_loader_returns_dataframe():
    """担当案件DBをDataFrameとして返すこと"""
    loader = DbLoader.__new__(DbLoader)
    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = [
        {"担当者名": "田中", "ASP名": "asp_A", "案件ID": "A001", "媒体種別": "asp", "媒体アカウントID": ""},
        {"担当者名": "佐藤", "ASP名": "", "案件ID": "", "媒体種別": "google", "媒体アカウントID": "123-456"},
    ]
    loader.worksheet = mock_ws

    df = loader.load()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ["担当者名", "ASP名", "案件ID", "媒体種別", "媒体アカウントID"]


def test_db_loader_unique_persons():
    """担当者名一覧を重複なく返すこと"""
    loader = DbLoader.__new__(DbLoader)
    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = [
        {"担当者名": "田中", "ASP名": "asp_A", "案件ID": "A001", "媒体種別": "asp", "媒体アカウントID": ""},
        {"担当者名": "田中", "ASP名": "", "案件ID": "", "媒体種別": "google", "媒体アカウントID": "123-456"},
        {"担当者名": "佐藤", "ASP名": "", "案件ID": "", "媒体種別": "yahoo", "媒体アカウントID": "999"},
    ]
    loader.worksheet = mock_ws

    persons = loader.unique_persons()
    assert persons == ["田中", "佐藤"]
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

```bash
pytest tests/test_phase2.py -v
```

期待出力: `ImportError`

- [ ] **Step 3: DbLoader を実装する**

`phase2/db_loader.py` を作成:

```python
import os
import pandas as pd
import gspread
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()


class DbLoader:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]
    SHEET_NAME = "担当案件DB"

    def __init__(self):
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            scopes=self.SCOPES,
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(os.environ["ASSIGNMENT_SPREADSHEET_ID"])
        self.worksheet = spreadsheet.worksheet(self.SHEET_NAME)

    def load(self) -> pd.DataFrame:
        """担当案件DBをDataFrameとして返す"""
        records = self.worksheet.get_all_records()
        return pd.DataFrame(records)

    def unique_persons(self) -> list[str]:
        """担当者名を重複なく順番通りに返す"""
        df = self.load()
        return list(dict.fromkeys(df["担当者名"].tolist()))
```

- [ ] **Step 4: テストを実行してパスすることを確認する**

```bash
pytest tests/test_phase2.py -v
```

期待出力: `2 passed`

- [ ] **Step 5: コミットする**

```bash
git add phase2/db_loader.py tests/test_phase2.py
git commit -m "feat: 担当案件DBローダーを実装"
```

---

## Task 8: Phase2 個人別CSV生成を実装する

**Files:**
- Create: `phase2/personal_csv_builder.py`
- Modify: `tests/test_phase2.py`（テスト追加）

- [ ] **Step 1: テストを追加する**

`tests/test_phase2.py` に追記:

```python
import os
from phase2.personal_csv_builder import PersonalCsvBuilder


def test_builder_filters_by_person(tmp_path):
    """田中さん分のデータのみが抽出されること"""
    db_df = pd.DataFrame([
        {"担当者名": "田中", "ASP名": "asp_A", "案件ID": "A001", "媒体種別": "asp", "媒体アカウントID": ""},
        {"担当者名": "佐藤", "ASP名": "asp_A", "案件ID": "A002", "媒体種別": "asp", "媒体アカウントID": ""},
    ])
    raw_df = pd.DataFrame([
        {"item_id": "A001", "date": "2026-05-29", "clicks": 100},
        {"item_id": "A002", "date": "2026-05-29", "clicks": 200},
    ])
    mapping = {"join_key_db": "案件ID", "join_key_raw": "item_id"}

    builder = PersonalCsvBuilder.__new__(PersonalCsvBuilder)
    result = builder._filter_for_person("田中", db_df, raw_df, mapping)

    assert len(result) == 1
    assert result.iloc[0]["item_id"] == "A001"


def test_builder_outputs_empty_csv_when_no_match(tmp_path):
    """担当案件が0件でも空CSVが生成されること（エラーにならない）"""
    db_df = pd.DataFrame([
        {"担当者名": "田中", "ASP名": "asp_A", "案件ID": "A001", "媒体種別": "asp", "媒体アカウントID": ""},
    ])
    raw_df = pd.DataFrame([
        {"item_id": "A999", "date": "2026-05-29", "clicks": 100},  # 一致しない
    ])
    mapping = {"join_key_db": "案件ID", "join_key_raw": "item_id"}

    builder = PersonalCsvBuilder.__new__(PersonalCsvBuilder)
    result = builder._filter_for_person("田中", db_df, raw_df, mapping)

    assert len(result) == 0
    assert isinstance(result, pd.DataFrame)
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

```bash
pytest tests/test_phase2.py::test_builder_filters_by_person -v
```

期待出力: `ImportError`

- [ ] **Step 3: PersonalCsvBuilder を実装する**

`phase2/personal_csv_builder.py` を作成:

```python
import os
import pandas as pd
import yaml
import logging
from datetime import date
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class PersonalCsvBuilder:
    def __init__(self, mapping_config_path: str = "config/db_mapping.yaml"):
        with open(mapping_config_path) as f:
            self.mappings = yaml.safe_load(f)["mappings"]

    def _filter_for_person(
        self,
        person: str,
        db_df: pd.DataFrame,
        raw_df: pd.DataFrame,
        mapping: dict,
    ) -> pd.DataFrame:
        person_db = db_df[db_df["担当者名"] == person]
        join_keys = person_db[mapping["join_key_db"]].tolist()
        return raw_df[raw_df[mapping["join_key_raw"]].isin(join_keys)].copy()

    def build(self, db_df: pd.DataFrame, raw_dfs: dict[str, pd.DataFrame], output_dir: str, date_str: str) -> None:
        """
        db_df: 担当案件DB全体のDataFrame
        raw_dfs: {"asp": DataFrame, "google": DataFrame, "yahoo": DataFrame}
        output_dir: 出力ディレクトリパス
        """
        os.makedirs(output_dir, exist_ok=True)
        persons = list(dict.fromkeys(db_df["担当者名"].tolist()))

        for person in persons:
            frames = []
            for media_type, raw_df in raw_dfs.items():
                if media_type not in self.mappings:
                    logger.warning(f"マッピング未定義の媒体をスキップ: {media_type}")
                    continue
                filtered = self._filter_for_person(person, db_df, raw_df, self.mappings[media_type])
                frames.append(filtered)

            result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            out_path = os.path.join(output_dir, f"{person}_{date_str}.csv")
            result.to_csv(out_path, index=False, encoding="utf-8-sig")
            logger.info(f"{person}: {len(result)}行 → {out_path}")
```

- [ ] **Step 4: テストを実行してパスすることを確認する**

```bash
pytest tests/test_phase2.py -v
```

期待出力: `4 passed`

- [ ] **Step 5: コミットする**

```bash
git add phase2/personal_csv_builder.py tests/test_phase2.py
git commit -m "feat: 個人別CSV生成を実装"
```

---

## Task 9: Phase3 Excelライターを実装する

**Files:**
- Create: `phase3/excel_writer.py`
- Create: `tests/test_phase3.py`

- [ ] **Step 1: テストを作成する**

`tests/test_phase3.py` を作成:

```python
import pytest
import pandas as pd
import openpyxl
from pathlib import Path
from phase3.excel_writer import ExcelWriter


@pytest.fixture
def template_xlsx(tmp_path):
    """テスト用の簡易Excelテンプレートを作成する"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "日報"
    ws["A1"] = "ヘッダー行1"
    ws["A2"] = "ヘッダー行2"
    path = tmp_path / "template.xlsx"
    wb.save(path)
    return str(path)


def test_excel_writer_writes_correct_cells(template_xlsx, tmp_path):
    """mapping.yamlに従って正しいセルに値が書き込まれること"""
    mapping = {
        "sheet_name": "日報",
        "data_start_row": 3,
        "mappings": [
            {"csv_col": "clicks", "excel_col": "B"},
            {"csv_col": "cost", "excel_col": "C"},
        ],
    }
    df = pd.DataFrame([{"clicks": 100, "cost": 5000}])
    output_path = str(tmp_path / "output.xlsx")

    writer = ExcelWriter(mapping)
    writer.write(template_xlsx, df, output_path)

    wb = openpyxl.load_workbook(output_path)
    ws = wb["日報"]
    assert ws["B3"].value == 100
    assert ws["C3"].value == 5000


def test_excel_writer_preserves_existing_cells(template_xlsx, tmp_path):
    """書き込み対象外のセルが変更されていないこと"""
    mapping = {
        "sheet_name": "日報",
        "data_start_row": 3,
        "mappings": [{"csv_col": "clicks", "excel_col": "B"}],
    }
    df = pd.DataFrame([{"clicks": 100}])
    output_path = str(tmp_path / "output.xlsx")

    writer = ExcelWriter(mapping)
    writer.write(template_xlsx, df, output_path)

    wb = openpyxl.load_workbook(output_path)
    ws = wb["日報"]
    assert ws["A1"].value == "ヘッダー行1"  # 既存セルが保持されていること
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

```bash
pytest tests/test_phase3.py -v
```

期待出力: `ImportError`

- [ ] **Step 3: ExcelWriter を実装する**

`phase3/excel_writer.py` を作成:

```python
import logging
import pandas as pd
import openpyxl
import yaml
from openpyxl.utils import column_index_from_string

logger = logging.getLogger(__name__)


class ExcelWriter:
    def __init__(self, mapping: dict):
        self.sheet_name = mapping["sheet_name"]
        self.data_start_row = mapping["data_start_row"]
        self.col_mappings = mapping["mappings"]

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ExcelWriter":
        with open(yaml_path) as f:
            return cls(yaml.safe_load(f))

    def write(self, template_path: str, df: pd.DataFrame, output_path: str) -> None:
        """テンプレートExcelにDataFrameの値を書き込んで output_path へ保存する"""
        wb = openpyxl.load_workbook(template_path, keep_vba=True)
        ws = wb[self.sheet_name]

        for row_idx, row in enumerate(df.itertuples(index=False), start=self.data_start_row):
            for mapping in self.col_mappings:
                csv_col = mapping["csv_col"]
                excel_col = mapping["excel_col"]
                if csv_col not in df.columns:
                    logger.warning(f"CSV列が見つかりません、スキップ: {csv_col}")
                    continue
                col_num = column_index_from_string(excel_col)
                ws.cell(row=row_idx, column=col_num, value=getattr(row, csv_col, None))

        wb.save(output_path)
        logger.info(f"Excel書き込み完了: {output_path}")
```

- [ ] **Step 4: テストを実行してパスすることを確認する**

```bash
pytest tests/test_phase3.py -v
```

期待出力: `2 passed`

- [ ] **Step 5: コミットする**

```bash
git add phase3/excel_writer.py tests/test_phase3.py
git commit -m "feat: Excelライターを実装"
```

---

## Task 10: Phase3 レポートアーカイバーを実装する

**Files:**
- Create: `phase3/report_archiver.py`
- Modify: `tests/test_phase3.py`（テスト追加）

- [ ] **Step 1: テストを追加する**

`tests/test_phase3.py` に追記:

```python
from unittest.mock import MagicMock, patch
from phase3.report_archiver import ReportArchiver


def test_report_archiver_uploads_to_correct_folder():
    """report/YYYY-MM-DD/ フォルダへアップロードされること"""
    archiver = ReportArchiver.__new__(ReportArchiver)
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {"files": [{"id": "report_folder_id"}]}
    mock_service.files().create().execute.return_value = {"id": "date_folder_id"}
    archiver.service = mock_service
    archiver.root_folder_id = "root_id"

    # フォルダ取得のみテスト（実際のアップロードはDriveUploaderと同様）
    report_folder_id = archiver._get_or_create_folder("report", "root_id")
    assert report_folder_id == "report_folder_id"
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

```bash
pytest tests/test_phase3.py::test_report_archiver_uploads_to_correct_folder -v
```

期待出力: `ImportError`

- [ ] **Step 3: ReportArchiver を実装する**

`phase3/report_archiver.py` を作成:

```python
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()


class ReportArchiver:
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    def __init__(self):
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            scopes=self.SCOPES,
        )
        self.service = build("drive", "v3", credentials=creds)
        self.root_folder_id = os.environ["DRIVE_ROOT_FOLDER_ID"]

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
            f" and '{parent_id}' in parents and trashed=false"
        )
        res = self.service.files().list(q=query, fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self.service.files().create(body=meta, fields="id").execute()
        return folder["id"]

    def upload_report(self, local_path: str, filename: str, date_str: str) -> str:
        """完成ExcelをDrive report/YYYY-MM-DD/ へアップロードする"""
        report_folder_id = self._get_or_create_folder("report", self.root_folder_id)
        date_folder_id = self._get_or_create_folder(date_str, report_folder_id)

        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        media = MediaFileUpload(local_path, mimetype=mime)
        file_meta = {"name": filename, "parents": [date_folder_id]}
        uploaded = (
            self.service.files().create(body=file_meta, media_body=media, fields="id").execute()
        )
        return uploaded["id"]
```

- [ ] **Step 4: テストを実行してパスすることを確認する**

```bash
pytest tests/test_phase3.py -v
```

期待出力: `3 passed`

- [ ] **Step 5: コミットする**

```bash
git add phase3/report_archiver.py tests/test_phase3.py
git commit -m "feat: レポートアーカイバーを実装"
```

---

## Task 11: GitHub Actions ワークフローを作成する

**Files:**
- Create: `.github/workflows/daily_report.yml`

- [ ] **Step 1: ワークフローファイルを作成する**

`.github/workflows/daily_report.yml` を作成:

```yaml
name: Daily Report Automation

on:
  schedule:
    - cron: '0 23 * * 0-4'  # 月〜金 日本時間 08:00（UTC 前日 23:00）
  workflow_dispatch:          # 手動実行

env:
  GOOGLE_SERVICE_ACCOUNT_JSON: credentials/service_account.json
  DRIVE_ROOT_FOLDER_ID: ${{ secrets.DRIVE_ROOT_FOLDER_ID }}
  ASSIGNMENT_SPREADSHEET_ID: ${{ secrets.ASSIGNMENT_SPREADSHEET_ID }}
  GOOGLE_ADS_SPREADSHEET_ID: ${{ secrets.GOOGLE_ADS_SPREADSHEET_ID }}
  YAHOO_ADS_ACCESS_TOKEN: ${{ secrets.YAHOO_ADS_ACCESS_TOKEN }}
  YAHOO_ADS_ACCOUNT_IDS: ${{ secrets.YAHOO_ADS_ACCOUNT_IDS }}
  ASP_A_URL: ${{ secrets.ASP_A_URL }}
  ASP_A_USERNAME: ${{ secrets.ASP_A_USERNAME }}
  ASP_A_PASSWORD: ${{ secrets.ASP_A_PASSWORD }}

jobs:
  phase1:
    name: Phase1 データ取得
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Python セットアップ
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 依存パッケージインストール
        run: |
          pip install -r requirements.txt
          playwright install chromium

      - name: サービスアカウントキーを配置
        run: |
          mkdir -p credentials
          echo '${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}' > credentials/service_account.json

      - name: ASP CSV ダウンロード
        run: python -m phase1.asp_downloader

      - name: Google広告データ取得
        run: python -m phase1.google_ads_fetcher

      - name: Yahoo広告データ取得
        run: python -m phase1.yahoo_ads_fetcher

  phase2:
    name: Phase2 個人別CSV生成
    needs: phase1
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - name: サービスアカウントキーを配置
        run: |
          mkdir -p credentials
          echo '${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}' > credentials/service_account.json
      - name: 個人別CSV生成
        run: python -m phase2.personal_csv_builder

  phase3:
    name: Phase3 Excel書き込み・保存
    needs: phase2
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - name: サービスアカウントキーを配置
        run: |
          mkdir -p credentials
          echo '${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}' > credentials/service_account.json
      - name: Excel書き込みと保存
        run: |
          python -m phase3.excel_writer
          python -m phase3.report_archiver
```

- [ ] **Step 2: GitHub Secretsに以下の値を登録する（GitHubリポジトリの Settings > Secrets > Actions）**

```
GOOGLE_SERVICE_ACCOUNT_JSON  （サービスアカウントのJSONの中身を貼り付け）
DRIVE_ROOT_FOLDER_ID
ASSIGNMENT_SPREADSHEET_ID
GOOGLE_ADS_SPREADSHEET_ID
YAHOO_ADS_ACCESS_TOKEN
YAHOO_ADS_ACCOUNT_IDS
ASP_A_URL
ASP_A_USERNAME
ASP_A_PASSWORD
```

- [ ] **Step 3: ワークフローファイルをコミットする**

```bash
git add .github/workflows/daily_report.yml
git commit -m "feat: GitHub Actionsワークフローを追加"
```

- [ ] **Step 4: workflow_dispatch で手動実行して動作確認する**

GitHubリポジトリの Actions タブ → Daily Report Automation → Run workflow

期待動作: Phase1→Phase2→Phase3 の順にJobが緑になること

---

## Task 12: CLAUDE.md を作成する

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: CLAUDE.md を作成する**

```markdown
# 日報自動化プロジェクト

## 基本方針
- 既存の日報 Excel フォーマットは絶対に変更しない
- 認証情報は必ず .env から読み込む。コードに直書き禁止
- 各 Phase は独立して単体テストできる構造を維持する

## 実装順序
1. Phase 1 を完成・テストしてから Phase 2 に進む
2. Phase 2 を完成・テストしてから Phase 3 に進む
3. 各 Phase の「テスト完了条件」を必ず確認すること

## テスト実行
\`\`\`bash
pytest tests/ -v
\`\`\`

## 使用技術
- Python 3.11+, Playwright, gspread, pandas, openpyxl
- google-api-python-client（Drive API v3・サービスアカウント認証）
- Yahoo! 広告 API, GitHub Actions
```

- [ ] **Step 2: コミットする**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.mdを追加"
```

---

## 全テスト実行（最終確認）

- [ ] 全テストをまとめて実行する

```bash
pytest tests/ -v
```

期待出力: `9 passed`（各フェーズのテストがすべてパス）
