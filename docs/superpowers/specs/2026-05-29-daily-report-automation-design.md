# 日報自動化システム 設計ドキュメント

**日付：** 2026-05-29  
**ステータス：** 承認済み

---

## 概要

広告運用チームの日報作成を自動化する。ASP・Google広告・Yahoo広告からデータを取得し、担当者別に既存日報ExcelへデータをフィットするPythonシステムをGitHub Actionsで毎朝実行する。

---

## アーキテクチャ方針

- **フェーズ別スクリプト構成：** `phase1/`・`phase2/`・`phase3/` を独立したPythonモジュールとして分離し、各フェーズ単体でテスト・実行可能にする
- **GitHub Actions：** Phase1→2→3をJobチェーンで順番に実行（`needs:` で依存関係を定義）
- **認証情報：** すべてGitHub Secretsに登録し、`.env` 経由で読み込む（コードへの直書き禁止）
- **既存Excelフォーマット：** 一切変更しない

---

## ディレクトリ構成

```
daily-report-automation/
├── .env                        # 認証情報（git管理外）
├── .github/
│   └── workflows/
│       └── daily_report.yml   # GitHub Actions（毎朝実行）
├── config/
│   ├── asp_sites.yaml         # ASPサイトのURL・ログイン設定
│   ├── db_mapping.yaml        # 担当案件DBの列マッピング定義
│   └── excel_mapping.yaml     # CSV→Excelセル対応表
├── phase1/
│   ├── asp_downloader.py      # ASP CSVダウンロード（Playwright RPA）
│   ├── google_ads_fetcher.py  # Google Ads Scriptsのスプレッドシートを取得
│   ├── yahoo_ads_fetcher.py   # Yahoo広告APIからデータ取得
│   └── drive_uploader.py      # Drive raw/ フォルダへ保存
├── phase2/
│   ├── db_loader.py           # 担当案件DBスプレッドシートを読込
│   └── personal_csv_builder.py # 個人別CSVを生成
├── phase3/
│   ├── excel_writer.py        # openpyxlでExcelへ書き込み
│   └── report_archiver.py     # Drive report/ フォルダへ保存
├── tests/
│   ├── test_phase1.py
│   ├── test_phase2.py
│   └── test_phase3.py
└── requirements.txt
```

---

## GitHub Actions ワークフロー

```yaml
name: Daily Report Automation
on:
  schedule:
    - cron: '0 23 * * 0-4'  # 日本時間 毎朝8時（UTC前日23時）月〜金
  workflow_dispatch:

jobs:
  phase1:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: python -m phase1.asp_downloader
      - run: python -m phase1.google_ads_fetcher
      - run: python -m phase1.yahoo_ads_fetcher
      - run: python -m phase1.drive_uploader

  phase2:
    needs: phase1
    runs-on: ubuntu-latest
    steps:
      - run: python -m phase2.personal_csv_builder

  phase3:
    needs: phase2
    runs-on: ubuntu-latest
    steps:
      - run: python -m phase3.excel_writer
      - run: python -m phase3.report_archiver
```

---

## Phase1：データ取得 → Drive保存

### ASP（Playwright RPA）
- 1社目のASPサイトにログイン → CSV一括ダウンロード
- ASP設定は `config/asp_sites.yaml` で管理（URL・ログイン手順を設定ファイルに分離、多社対応を考慮）

### Google広告
- Google Ads Scripts側でスプレッドシートにデータ書き出し（Scripts自体はGoogle側で毎朝実行）
- Python側は `gspread` でスプレッドシートを読み込み → CSV変換

### Yahoo!広告
- `requests` でYahoo広告APIを叩いてJSONを取得 → pandas でCSV変換
- アカウントIDは `.env` から読み込み

### Drive保存
- サービスアカウント認証（`google-api-python-client`）
- `raw/YYYY-MM-DD/` フォルダへ各CSVをアップロード（フォルダは自動作成）

### Drive構成（出力）
```
daily-report-automation/
└── raw/
    └── YYYY-MM-DD/
        ├── asp_A.csv
        ├── google_ads.csv
        └── yahoo_ads.csv
```

---

## Phase2：個人別CSV生成

### 担当案件DBの読み込み
- `gspread` でGoogleスプレッドシート「担当案件DB」を読み込み → pandas DataFrame化
- シート名：`担当案件DB`

| 列名 | 内容 |
|------|------|
| 担当者名 | 担当者の氏名 |
| ASP名 | ASPの識別名 |
| 案件ID | raw CSVの結合キー |
| 媒体種別 | google / yahoo / asp |
| 媒体アカウントID | 広告アカウントID |

### 照合ロジック
- Drive の `raw/YYYY-MM-DD/` から各CSVをダウンロード
- `config/db_mapping.yaml` に定義されたキー列でJOIN
- 担当者ごとにフィルタリングして個人別DataFrameを生成

### エラーハンドリング
- 担当案件が0件でも空CSVを生成（エラーにしない）
- raw CSVが存在しない媒体は警告ログを出してスキップ

### Drive構成（出力）
```
daily-report-automation/
└── personal/
    └── YYYY-MM-DD/
        ├── tanaka_2026-05-29.csv
        └── sato_2026-05-29.csv
```

---

## Phase3：Excel書き込み → Drive保存

### Excel書き込み
- テンプレートを Drive `template/` フォルダから毎回ダウンロード
- `openpyxl` の `load_workbook(keep_vba=True)` で読み込み
- `config/excel_mapping.yaml` に従って値を書き込み
- 数式・条件付き書式・書式設定は一切変更しない
- 担当者ごとにコピーを作成してから書き込み、別名保存（元ファイルを上書きしない）

### エラーハンドリング
- 個人別CSVが空の場合はExcel生成をスキップ（ログに記録）
- セルマッピングに存在しない列名はワーニングを出してスキップ

### Drive構成（出力）
```
daily-report-automation/
├── template/
│   └── 日報テンプレート.xlsx      # マスターテンプレート
└── report/
    └── YYYY-MM-DD/
        ├── tanaka_日報_2026-05-29.xlsx
        └── sato_日報_2026-05-29.xlsx
```

---

## 使用技術

| 技術 | 用途 |
|------|------|
| Python 3.11+ | メイン言語 |
| Playwright | ASP RPA |
| gspread | Googleスプレッドシート読み込み |
| pandas | CSV処理・JOIN |
| openpyxl | Excel書き込み（書式保持） |
| google-api-python-client | Drive API（サービスアカウント） |
| requests | Yahoo広告API |
| GitHub Actions | スケジュール実行 |

---

## テスト完了条件

### Phase1
- `raw/YYYY-MM-DD/asp_A.csv` などが手動実行で正しく生成される
- 列名・日付フォーマットが想定通りであること

### Phase2
- 担当者分のCSVに、その担当者が担当する案件の行だけが含まれる
- 他担当者のデータが混入していないこと
- 担当案件が0件の場合にエラーでなく空CSVが生成されること

### Phase3
- 既存ExcelのフォーマットがPhase3実行後も崩れていないこと
- 指定セルに正しい値が入っていること
- 数式・条件付き書式が壊れていないこと
