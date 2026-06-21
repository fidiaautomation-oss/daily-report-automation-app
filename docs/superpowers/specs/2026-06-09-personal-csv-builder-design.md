# Phase2: 個人別CSV生成 設計ドキュメント

**日付：** 2026-06-09
**ステータス：** 承認済み

---

## 概要

Google Drive `raw/YYYY-MM-DD/` のCSV群と「【運用チーム】案件管理シート」を突合し、運用者ごとに担当案件のデータだけを集めた個人別CSV（明細＋集計の2本）を生成して Drive `personal/YYYY-MM-DD/` に保存する。

- 案件管理シート: `1sfccIFoXJbMciIGPi7RzIJ3knqdpbAlnZhpBJmiD6iw`
- 既存スタブ `phase2/personal_csv_builder.py` を全面書き換え

---

## 案件管理シートの構造

| タブ | 構造 | 管理者 |
|------|------|--------|
| `案件（◯◯さん）` | No. / ASP名 / 案件名 / サイトID（任意）。ヘッダーは2行目 | 運用者が入力 |
| `配信プラットフォーム（◯◯さん）` | No. / 配信プラットフォーム / 取得単位 / キャンペーンor広告グループID | 運用者が入力 |
| `案件名マスタ`（新設） | ASP名 / 案件名。毎朝自動更新 | システムが自動生成 |
| `DB` | ASP名マスタ（プルダウン用） | 固定 |

- タブ名の `（<名前>）` 部分をパースして運用者を自動検出する
- 運用者が増えたらタブを複製するだけで自動的に対象へ追加される
- `案件名マスタ` は raw CSV から抽出した「ASP名＋案件名」の全組み合わせ。
  運用者は案件名をプルダウンで選択する（完全一致を保証する仕組み）

### ASP名の対応（DBタブ ⇔ raw CSVファイル）

| シートのASP名 | rawファイル |
|---|---|
| A8.net | a8net_a.csv, a8net_b.csv |
| アクセストレード | accesstrade.csv |
| afb | affiliateb.csv |
| Felmat | felmat_f.csv, felmat_m.csv |
| fukuro | fukuro.csv |
| funny | funny.csv |
| inventas | invgold.csv |
| リンクシェア | linkshare.csv |
| レントラックス | rentracks.csv |
| RESULTPLUS2 | resultplus2.csv |
| sonic | sonic.csv |

---

## raw CSV の正規化

ASPごとの列名差を `config/normalize_mapping.yaml` で吸収し、統一スキーマに変換する。

### 統一スキーマ（ASP明細）

| 列 | 内容 | ASPごとのソース列例 |
|----|------|----|
| date | 成果発生日時 | 発生日時 / 注文日 / 売上日時 / Conversion日時 等 |
| asp_name | シート側ASP名 | （ファイル名から決定） |
| case_name | 案件名 | プログラム名 / プロダクト / プロモーション / キャンペーン / 広告 / ECマーチャント名 / 広告名 |
| site_id | サイトID | サイトID（無いASPは空） |
| reward | 報酬額 | 発生金額 / 報酬 / 報酬額 / 成果報酬（税抜） / 成果報酬額[円] / メディア報酬額 |
| count | 件数 | 固定1（1行=1成果） |

### Yahoo広告（yahoo_ads.csv）

`campaign_id` / `adgroup_id` 列を Phase1 fetcher に追加する（突合キー）。
スキーマ: date / account_id / account_name / campaign_id / campaign_name / adgroup_id / adgroup_name / impressions / clicks / cost / conversions

### Google広告

アカウント情報確認中のため本設計ではプレースホルダ。突合ロジックはYahooと同一構造（媒体名で分岐）にして追加可能にしておく。

---

## 突合ロジック

- **ASP案件**: シートの「ASP名＋案件名」と正規化済み明細の「asp_name＋case_name」の**完全一致**。シートのサイトIDが入力されている場合は site_id でも絞り込む
- **広告（Yahoo）**: シートの「取得単位」が `キャンペーンID` なら campaign_id、`広告グループID` なら adgroup_id の一致

---

## 出力（運用者ごとに2本）

Drive `personal/YYYY-MM-DD/` へ保存（UTF-8 BOM付き）:

1. `<運用者>_明細.csv` — マッチした全明細行（ASP成果明細 + Yahoo広告行）
2. `<運用者>_集計.csv` — 1行=1案件/1広告ID:
   `種別(asp/yahoo) / asp_name または媒体 / case_name またはID / 発生件数 / 報酬合計 / 広告費 / クリック / インプレッション / CV`

---

## エラーハンドリング

| ケース | 挙動 |
|--------|------|
| 担当案件0件の運用者 | 空CSVを生成（エラーにしない） |
| シートの案件名がCSVに不一致 | 警告ログ＋集計に件数0行を出力 |
| raw CSVが存在しないASP | 警告ログしてスキップ |
| 案件タブはあるが配信プラットフォームタブが無い（逆も） | ある方だけ処理 |

---

## 付随対応

1. **drive_uploader の同名上書き対応**: 現在同名ファイルが重複保存される。アップロード前に同名検索→存在すれば update に変更
2. **Yahoo fetcher に CAMPAIGN_ID / ADGROUP_ID を追加**（有効フィールド確認済み）
3. **案件名マスタの自動更新**: personal_csv_builder 実行時に raw から抽出して `案件名マスタ` タブへ書き込み、`案件（*）` タブの案件名列にデータ検証（プルダウン）を設定
4. 認証は既存 `credentials/token.json`（drive スコープ）を流用。Sheets API は有効化済み

---

## テスト完了条件

- ユニットテスト: 正規化・突合・集計ロジック（pytest、シート/DriveはモックまたはローカルCSV）
- 通しテスト: シートにテスト案件を入力 → `personal/YYYY-MM-DD/井上さん_明細.csv` と `_集計.csv` が生成され、担当案件のデータのみ含まれること
- 案件名マスタタブが自動生成・更新されること
- raw/2026-06-08 の yahoo_ads.csv 重複が解消されること（上書き動作）
