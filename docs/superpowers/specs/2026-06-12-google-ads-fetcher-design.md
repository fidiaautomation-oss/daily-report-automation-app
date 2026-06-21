# Google広告フェッチャー 設計ドキュメント

**日付：** 2026-06-12
**ステータス：** 承認済み

---

## 概要

Google広告のレポートを **Google Ads Scripts**（MCCレベル実行）でスプレッドシートに書き出し、
Python側でそのシートを読み込んで `raw/YYYY-MM-DD/google_ads.csv` として Drive に保存する。
取得粒度・項目は Yahoo広告と統一し、Phase2 の突合を共通化する。

### アカウント階層
```
自動化用MCC（スクリプト実行アカウント）
└── 各MCC（広告アカウントを束ねる）
    └── 広告アカウント × 4種
```
Google Ads Scripts を最上位の自動化用MCCに設置すると、`AdsManagerApp.accounts()` で
配下（ネストされたMCC配下を含む）の全広告アカウントを巡回できる。

---

## 構成

### 1. Google Ads Script（`scripts/google_ads_export.gs`）
- 最上位MCCにスクリプトを設置し、毎朝スケジュール実行（ユーザー設定）
- `AdsManagerApp.accounts()` で配下の全広告アカウントを巡回
- 各アカウントで GAQL レポートを実行（前日・広告グループ単位）
- 結果を出力先スプレッドシートの `google_ads` シートへ書き出し（毎回クリア→全書き込み）

GAQLクエリ:
```sql
SELECT segments.date, customer.id, customer.descriptive_name,
       campaign.id, campaign.name, ad_group.id, ad_group.name,
       metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
FROM ad_group
WHERE segments.date DURING YESTERDAY
```
- `cost_micros / 1,000,000` で通貨単位のコストに変換
- 出力列（Yahooと統一）:
  `date, account_id, account_name, campaign_id, campaign_name, adgroup_id, adgroup_name,
   impressions, clicks, cost, conversions`

### 2. Python フェッチャー（`phase1/google_ads_fetcher.py`）
- `GOOGLE_ADS_SHEET_ID` のスプレッドシート `google_ads` シートを Sheets API で読込
- DataFrame 化し、`date` が前日のみであることを確認（保険でフィルタ）
- `raw/YYYY-MM-DD/google_ads.csv`（UTF-8 BOM）として Drive へアップロード（同名上書き）

### 3. Phase2 統合（`phase2/personal_csv_builder.py`）
- `normalize_google()` を追加（Yahooと同一スキーマ）
- `build_person()` で配信プラットフォーム「Google」を Yahoo と同様にキャンペーン/広告グループIDで突合
- 広告マスタ（`extract_ad_master`）に Google のキャンペーン・広告グループも追加
  → 案件管理シートの配信PFタブで Google も連動プルダウン・ID自動反映が効く

---

## 環境変数

| 変数 | 内容 |
|------|------|
| `GOOGLE_ADS_SHEET_ID` | Google Ads Scripts の出力先スプレッドシートID（新規作成・OAuthアカウントと共有） |

※ Google Ads API の developer_token 等は不要（Scripts方式のため）

---

## セットアップ手順（ユーザー作業）

1. 空のGoogleスプレッドシートを新規作成し、自動化用Googleアカウントに編集権限を付与
2. そのスプレッドシートIDを `.env` の `GOOGLE_ADS_SHEET_ID` に設定
3. 最上位の自動化用MCCの「ツールと設定 → 一括操作 → スクリプト」に
   `scripts/google_ads_export.gs` を貼り付け、`SHEET_URL` を上記シートURLに設定
4. スクリプトを承認・プレビュー実行して `google_ads` シートに出力されることを確認
5. 毎日（毎朝6〜7時）実行のスケジュールを設定

---

## エラーハンドリング

| ケース | 挙動 |
|--------|------|
| スクリプト側でアカウント取得失敗 | そのアカウントをスキップ（スクリプトログに記録） |
| シートが空（前日実績なし） | 空CSVを生成 |
| `GOOGLE_ADS_SHEET_ID` 未設定 | 警告ログしてGoogle取得をスキップ（他媒体は継続） |

---

## テスト完了条件

- Python: シート読込→CSV変換→Drive保存のユニットテスト（Sheetsはモック）
- Phase2: Google配信プラットフォームの突合テスト（Yahooと同等）
- 通し: スクリプト実行後、`raw/YYYY-MM-DD/google_ads.csv` が生成され、
  `date` が前日のみ・列がYahooと一致すること
