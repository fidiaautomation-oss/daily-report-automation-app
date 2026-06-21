# 日報自動化プロジェクト — Claude Code 引き継ぎドキュメント

## プロジェクト概要

広告運用チームにおける日報作成を自動化する。
担当者ごとに担当案件が異なるため、複数の情報源から担当者別に必要データだけを抽出し、
既存フォーマットの日報 Excel へ自動反映する仕組みを構築する。

---

## 情報源

| 種別 | 取得方法 | 備考 |
|------|----------|------|
| ASP 各社（複数社） | CSV ダウンロード | 各社のサイトからRPAで取得想定 |
| Google 広告 | API または Google Ads Scripts | Scripts の方が認証が楽。後で API 移行も可 |
| Yahoo 広告 | Yahoo! 広告 API | アカウント ID 一覧が必要 |

---

## 出力先

- **Google Drive**（スプレッドシート / Excel）
- まずはドラフト自動生成 → 担当者がレビュー → 将来的に完全自動投稿

---

## 自動化の方針

- **既存の日報 Excel フォーマットをそのまま使う**（フォーマット変更なし）
- **担当案件 DB をスプレッドシートで管理**し、担当者ごとに必要な行だけを抽出
- **段階的テスト**：Phase ごとに動作確認してから次へ進む

---

## 3フェーズ構成

```
Phase 1 │ 情報源の一括取得 → Drive 格納
Phase 2 │ Drive データ × 担当案件 DB → 個人別 CSV 生成
Phase 3 │ 個人別 CSV → 既存日報 Excel 自動反映
```

---

## Phase 1 詳細：情報源の一括取得 → Drive 格納

### 目的
毎朝、全データソースから最新データを取得し、Drive の `raw/YYYY-MM-DD/` フォルダへ保存する。

### Drive フォルダ構成（出力）
```
My Drive/
└── daily-report-automation/
    └── raw/
        └── YYYY-MM-DD/
            ├── asp_A.csv
            ├── asp_B.csv
            ├── google_ads.csv
            └── yahoo_ads.csv
```

### テスト完了条件
- `raw/YYYY-MM-DD/asp_A.csv` などが手動実行で正しく生成される
- 列名・日付フォーマットが想定通りであること

### 実装上の注意
- 認証情報は `.env` に分離し、コードに直書きしない

---

## Phase 2 詳細：担当案件 DB と照合 → 個人別 CSV 生成

### 目的
担当案件 DB スプレッドシートを読み込み、各担当者が担当する案件の行だけを raw データから抽出して個人別 CSV を生成する。

### 担当案件 DB スプレッドシートの設計（要事前設定）

シート名：`担当案件DB`

| 列名 | 内容 | 例 |
|------|------|----|
| `担当者名` | 担当者の氏名 | 田中 |
| `ASP名` | ASP の識別名 | asp_A |
| `案件ID` | raw CSV の結合キーになる ID | A00123 |
| `媒体種別` | google / yahoo / asp | google |
| `媒体アカウントID` | 広告アカウント ID（媒体の場合） | 123-456-7890 |

> **重要：** `案件ID` または `媒体アカウントID` が raw CSV 側のどの列と対応するかを
> 事前に確認し、`config/db_mapping.yaml` に定義しておく。

### Drive フォルダ構成（出力）
```
daily-report-automation/
└── personal/
    └── YYYY-MM-DD/
        ├── tanaka_2025-05-29.csv
        ├── sato_2025-05-29.csv
        └── ...
```

### テスト完了条件
- 田中さん分の CSV に、田中さんが担当する案件の行だけが含まれる
- 他担当者のデータが混入していないこと
- 担当案件が 0 件の場合にエラーでなく空 CSV が生成されること

---

## Phase 3 詳細：個人別 CSV → 既存日報 Excel 反映

### 目的
既存日報 Excel のフォーマット・書式を一切崩さずに、正しいセルへ値を書き込む。

### 事前設定作業（一度だけ）
既存日報 Excel の列構成を調査し、`config/excel_mapping.yaml` を作成する。

```yaml
# config/excel_mapping.yaml の例
sheet_name: "日報"
data_start_row: 5          # データが始まる行番号
mappings:
  - csv_col: "date"         excel_col: "B"
  - csv_col: "campaign"     excel_col: "C"
  - csv_col: "clicks"       excel_col: "F"
  - csv_col: "cv_count"     excel_col: "H"
  - csv_col: "cost"         excel_col: "J"
  - csv_col: "cpa"          excel_col: "K"
```

> このファイルさえ正確に作れば、Excel 本体には一切手を加えずに書き込める。

### Drive フォルダ構成（出力）
```
daily-report-automation/
└── report/
    └── YYYY-MM-DD/
        ├── tanaka_日報_2025-05-29.xlsx   ← ドラフト。担当者がレビュー
        ├── sato_日報_2025-05-29.xlsx
        └── ...
```

### 作成するスキル

| スキルファイル | 役割 |
|----------------|------|
| `skills/excel-mapper.md` | `excel_mapping.yaml` を読んで CSV→Excel セル対応表を生成 |
| `skills/cell-writer.md` | openpyxl で書式を維持したままセル書き込み |
| `skills/report-archiver.md` | 完成した Excel を Drive `report/` フォルダへ保存 |

### 実装上の注意
- `openpyxl` の `load_workbook(keep_vba=True)` を使い、既存書式・数式を保持する
- 数式セルへの上書きは行わない（`excel_mapping.yaml` の mappings に含めない）
- 前日比などの計算列は Excel 側の数式に任せる

### テスト完了条件
- 既存 Excel を開いてフォーマットが崩れていないこと
- 指定セルに正しい値が入っていること
- 数式・条件付き書式が壊れていないこと

## CLAUDE.md に書くべき内容（プロジェクト指示書）

Claude Code を起動したときに最初に読む指示書。以下の内容を記載する。

```markdown
# 日報自動化プロジェクト

## 基本方針
- 既存の日報 Excel フォーマットは絶対に変更しない
- 認証情報は必ず .env から読み込む。コードに直書き禁止
- 各 Phase は独立して単体テストできる構造を維持する
- スキルは skills/ フォルダに Markdown で定義し、再利用可能な単機能を保つ

## 実装順序
1. Phase 1 を完成・テストしてから Phase 2 に進む
2. Phase 2 を完成・テストしてから Phase 3 に進む
3. 各 Phase の「テスト完了条件」を必ず確認すること

## 使用技術
- Python 3.11+
- Playwrite(RPA)
- openpyxl（Excel 書き込み・書式保持）
- Google Drive API v3（ファイル保存）
- Google Ads API または Google Ads Scripts
- Yahoo! 広告 API
- pandas（CSV 処理・JOIN）

---

