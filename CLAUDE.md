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
```bash
pytest tests/ -v
```

## 使用技術
- Python 3.11+, Playwright, gspread, pandas, openpyxl
- google-api-python-client（Drive API v3・サービスアカウント認証）
- Yahoo! 広告 API, GitHub Actions

## config ファイルの設定（初回のみ）
- `config/excel_mapping.yaml`: 実際の日報Excelの列構成を確認して設定する
- `config/asp_sites.yaml`: ASPサイトのURLと操作手順を確認して設定する
- `config/db_mapping.yaml`: rawCSVの列名を確認してマッピングを設定する