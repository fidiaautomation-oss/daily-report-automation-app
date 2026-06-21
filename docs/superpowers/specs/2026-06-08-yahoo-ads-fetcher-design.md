# Yahoo広告フェッチャー 設計ドキュメント

**日付：** 2026-06-08  
**ステータス：** 承認済み

---

## 概要

Yahoo検索広告（Yahoo Search Ads API v14）から昨日分の広告パフォーマンスデータを取得し、Google Drive の `raw/YYYY-MM-DD/yahoo_ads.csv` へ保存する。既存の `phase1/yahoo_ads_fetcher.py` スタブを完全実装に置き換える。

---

## アーキテクチャ

```
YahooAdsFetcher
├── _get_access_token()          # refresh token → access token（自動更新）
├── _create_report(account_id)   # レポート定義作成・ジョブ投入
├── _poll_report(account_id, job_id)  # ステータスポーリング（完了まで待機）
├── _download_report(account_id, job_id)  # TSVダウンロード → DataFrame
└── fetch_to_csv(output_path)    # 全アカウント → 結合 → CSV保存
```

---

## 取得フィールド

| 出力列名 | Yahoo APIフィールド名 | 説明 |
|---------|---------------------|------|
| date | DAY | 日付（YYYY-MM-DD） |
| campaign_name | CAMPAIGN_NAME | キャンペーン名 |
| adgroup_name | ADGROUP_NAME | 広告グループ名 |
| impressions | IMPRESSIONS | インプレッション数 |
| clicks | CLICKS | クリック数 |
| cost | COST | 広告費用（円） |
| conversions | ALL_CONV | コンバージョン数（全て） |
| account_id | （付与） | 元アカウントID（複数アカウント識別用） |

出力粒度：広告グループ単位（CAMPAIGN_NAME + ADGROUP_NAME 両方を含む）

---

## Yahoo Search Ads API フロー

### 1. アクセストークン取得

```
POST https://biz-oauth.yahoo.co.jp/oauth2/v1/token
Body: grant_type=refresh_token&client_id=xxx&client_secret=xxx&refresh_token=xxx
Response: { "access_token": "...", "expires_in": 3600 }
```

毎回リフレッシュ（1時間有効だが、安全のため毎実行時に再取得する）。

### 2. レポート定義作成

```
POST https://ads-search.yahooapis.jp/api/v14/ReportDefinitionService/add
Headers: Authorization: Bearer {access_token}
         X-Z-AccountId: {account_id}
Body: レポート定義JSON（日付範囲・フィールド指定）
Response: { reportJobId: "xxx" }
```

レポート定義パラメータ：
- `reportType`: `ADGROUP`（広告グループ粒度）
- `dateRangeType`: `CUSTOM_DATE`
- `startDate` / `endDate`: 昨日の日付（YYYY-MM-DD）
- `fields`: `["DAY", "CAMPAIGN_NAME", "ADGROUP_NAME", "IMPRESSIONS", "CLICKS", "COST", "ALL_CONV"]`
- `format`: `TSV`

### 3. ステータスポーリング

```
GET https://ads-search.yahooapis.jp/api/v14/ReportDefinitionService/get
```

`status` が `COMPLETED` になるまで最大10分間、10秒おきにポーリング。
`FAILED` の場合はエラーとして処理。

### 4. レポートダウンロード

```
GET https://ads-search.yahooapis.jp/api/v14/ReportDefinitionService/download
Params: reportJobId={job_id}
```

TSV形式でダウンロード → pandasでDataFrame化。

---

## 複数アカウント対応

`YAHOO_ADS_ACCOUNT_IDS` 環境変数をカンマ区切りで指定。各アカウントに対して順次レポートを取得し、最後に `pd.concat` で結合する。

---

## 環境変数

| 変数名 | 内容 |
|--------|------|
| `YAHOO_ADS_CLIENT_ID` | OAuth2クライアントID |
| `YAHOO_ADS_CLIENT_SECRET` | OAuth2クライアントシークレット |
| `YAHOO_ADS_REFRESH_TOKEN` | リフレッシュトークン |
| `YAHOO_ADS_ACCOUNT_IDS` | アカウントIDのカンマ区切りリスト |

---

## エラーハンドリング

| ケース | 挙動 |
|--------|------|
| トークン取得失敗 | 例外を投げて処理中断（後続に意味がない） |
| レポートジョブ FAILED | 警告ログ＋そのアカウントをスキップ |
| ポーリングタイムアウト（10分超） | 警告ログ＋そのアカウントをスキップ |
| データ0件 | 空DataFrameとして処理（空CSVを保存） |
| 全アカウントスキップ | 空CSVを保存（Drive保存はスキップしない） |

---

## 出力

- **ファイル名：** `yahoo_ads.csv`
- **エンコーディング：** UTF-8 BOM付き（`utf-8-sig`）
- **保存先：** Google Drive `raw/YYYY-MM-DD/yahoo_ads.csv`
- **形式：** pandas CSV（ヘッダーあり、インデックスなし）

---

## 既存コードとの統合

- `phase1/yahoo_ads_fetcher.py` を全面書き換え
- `main()` 関数はそのまま維持（`drive_uploader.py` との連携を維持）
- `.env.example` に新しい環境変数4つを追記
- `requirements.txt` への追加は不要（`requests`・`pandas`は既存）

---

## 追補（2026-06-09）：アカウントID自動取得

実APIでの検証により、以下を確定・修正した。

### 実APIで判明した正しい仕様（v17）
- トークンエンドポイント： `https://biz-oauth.yahoo.co.jp/oauth/v1/token`
- APIバージョン： **v17**（ライブラリ13.x系）
- 全リクエストに必須ヘッダー `x-z-base-account-id`（対象アカウントID）
- `accountId` は数値型
- レポート定義フィールド名： `reportDateRangeType` / `reportDownloadFormat`(TSV) / `reportDownloadEncode`(UTF8)
- 取得フィールド： `DAY, CAMPAIGN_NAME, ADGROUP_NAME, IMPS, CLICKS, COST, ALL_CONV`
- ダウンロードは **POST**（GETは405）。CSVヘッダーは日本語のため列順で位置マッピング

### アカウントID自動取得
- `.env` の3つの文字列はアカウントIDではなく **ビジネスID**（リフレッシュトークンに対応）だった
- アカウントは `BaseAccountService/get`（`x-z-base-account-id` 不要）で列挙
- 1トークン＝多数アカウント（実測: 25 / 44 / MCC2 = 通常広告アカウント計69件）
- MCC（管理）アカウントはレポート対象外として除外
- `discover_accounts()`：全トークン横断でアカウント発見・重複排除（token→accounts のマッピング構築）
- `fetch_to_csv()`：毎回アカウントを自動発見してからレポート取得（アカウント増減に自動追従）

### .env への反映
- `python -m phase1.yahoo_ads_fetcher discover` で全アカウントIDを取得し、`.env` の
  自動生成ブロック（`# === YAHOO_ADS_ACCOUNTS (auto-generated) ===`）に書き戻す
- アカウントID→名称の対応をコメントとして併記（可視化用）
- `YAHOO_ADS_ACCOUNT_IDS` は手動管理不要（毎回の自動発見で動作）

### 出力カラム（更新）
`date, account_id, account_name, campaign_name, adgroup_name, impressions, clicks, cost, conversions`

## テスト完了条件

- 実行後に `raw/YYYY-MM-DD/yahoo_ads.csv` が生成されること
- CSV内の `date` 列が昨日の日付のみであること
- 複数アカウントIDが指定された場合、全アカウントのデータが結合されていること
- アカウントIDごとに `account_id` 列で識別できること
