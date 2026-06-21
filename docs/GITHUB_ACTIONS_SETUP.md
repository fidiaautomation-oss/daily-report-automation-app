# GitHub Actions セットアップ手順（Yahoo・Google広告の毎朝自動取得）

ASPはローカル実行のまま、**Yahoo広告・Google広告の取得をGitHub Actionsでクラウド自動化**する。

---

## 構成方針

- `daily-report-automation/` を **ホームから独立した専用gitリポジトリ** にする
- ワークフロー `.github/workflows/daily_report.yml` がリポジトリ直下に来る
- 認証はOAuth（`token.json`）の中身をGitHub Secretに登録（本番公開済みで無期限）

---

## 手順1：専用リポジトリとして初期化

> ⚠️ 現在 `daily-report-automation/` はホームディレクトリのgitリポジトリ配下にある。
> 下記は **新しい独立リポジトリ** として再初期化する手順。元のホームリポジトリには影響しない。
>
> ⚠️ **既存の `MasayukiMitomi/daily-report-automation` リポジトリには、ホームリポジトリ由来の
> `Claude/daily-report-automation/...` プレフィックス構造が既にpush済み**で、履歴が衝突する。
> **新しい空のGitHubリポジトリを作成して使う**こと（推奨）。

### 1-a. GitHubで新しい空リポジトリを作成
GitHub上で新規リポジトリ（例：`daily-report-automation-app`）を **README等なしの空**で作成する。

### 1-b. ローカルで独立リポジトリ化してpush
ターミナルで：

```bash
cd /Users/mitomi/Claude/daily-report-automation

# このディレクトリを新しい独立リポジトリとして初期化
git init

# 機密が混入しないことを確認（重要）
git add .
git status   # ← credentials/ .env *token*.json が「表示されない」ことを必ず確認！

# 表示されたら中断して .gitignore を確認。問題なければコミット
git commit -m "init: 日報自動化システム（Yahoo/Google広告クラウド対応）"

# 1-a で作った新リポジトリのURLに置き換える
git remote add origin https://github.com/MasayukiMitomi/<新リポジトリ名>.git
git branch -M main
git push -u origin main
```

> push時にユーザー名/パスワードを求められたら、GitHubの
> **Personal Access Token**（Settings → Developer settings → Tokens）を使う。

---

## 手順2：GitHub Secrets を登録

GitHubリポジトリの **Settings → Secrets and variables → Actions → New repository secret** で
以下6つを登録する。

| Secret名 | 値 | 取得元 |
|----------|----|----|
| `GOOGLE_OAUTH_TOKEN_JSON` | `credentials/token.json` の**中身全体**（JSON文字列） | 下記コマンドで表示 |
| `DRIVE_ROOT_FOLDER_ID` | Drive保存先ルートフォルダID | `.env` の同名値 |
| `GOOGLE_ADS_SHEET_ID` | Google広告出力シートID | `.env` の同名値 |
| `YAHOO_ADS_CLIENT_ID` | Yahoo広告 クライアントID | `.env` の同名値 |
| `YAHOO_ADS_CLIENT_SECRET` | Yahoo広告 クライアントシークレット | `.env` の同名値 |
| `YAHOO_ADS_REFRESH_TOKENS` | リフレッシュトークン（カンマ区切り） | `.env` の同名値 |

### token.json の中身を表示（コピー用）

```bash
cat /Users/mitomi/Claude/daily-report-automation/credentials/token.json
```

出力されたJSON全体をコピーし、`GOOGLE_OAUTH_TOKEN_JSON` の値に貼り付ける。

### .env の各値を表示

```bash
cd /Users/mitomi/Claude/daily-report-automation
grep -E "DRIVE_ROOT_FOLDER_ID|GOOGLE_ADS_SHEET_ID|YAHOO_ADS_CLIENT_ID|YAHOO_ADS_CLIENT_SECRET|YAHOO_ADS_REFRESH_TOKENS" .env
```

---

## 手順3：手動実行でテスト

GitHubリポジトリの **Actions → Daily Report - Yahoo & Google (Cloud) → Run workflow** で手動実行。

成功すると Drive `raw/YYYY-MM-DD/` に `yahoo_ads.csv` と `google_ads.csv` が保存される。

ログで以下を確認：
- `Yahoo広告 対象アカウント: 69件を自動発見`
- `google_ads.csv アップロード完了: ...`

---

## 実行タイミング

| 時刻(JST) | 処理 | 場所 |
|----------|------|------|
| 06:00-07:00 | Google Ads Scripts → スプレッドシート書き込み | Google（自動） |
| 08:00 | **本ワークフロー**：Yahoo・Google取得 → Drive保存 | GitHub Actions |
| （別途） | ASP取得 → Drive保存 | ローカル実行 |

> Google Ads Scripts は本ワークフローより前（6〜7時台）に完了している必要がある。

---

## 注意事項

- **OAuthトークンの無期限化**：OAuthアプリは本番公開済みのため `token.json` は失効しない。
  万一 `invalid_grant` が出たら、ローカルで `python -m phase1.google_auth_setup` を実行して
  `token.json` を再生成し、`GOOGLE_OAUTH_TOKEN_JSON` Secret を更新する。
- **ASPのクラウド化**：将来ASPもクラウド実行する場合、データセンターIPブロック対策
  （住宅プロキシ等）の追加検討が必要。
- **cron曜日**：現状は毎日実行。平日のみにする場合は `cron: '0 23 * * 0-4'` に変更。
