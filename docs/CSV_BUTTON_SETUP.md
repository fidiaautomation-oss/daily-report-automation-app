# 「CSVデータ作成」ボタン セットアップ手順

担当者ごとに、配信プラットフォーム/ASPごとの原本形式CSVをDriveへ生成する仕組み。

## 全体の流れ

```
[案件（◯◯さん）シートのボタン] 押下
    ↓ Apps Script (csv_request_button.gs)
[CSV生成リクエスト]タブに依頼行(pending)を追記
    ↓ 120秒おき・Mac launchd
phase2.request_watcher が pending を検知
    ↓
build_personal_split で担当者の担当行だけを
ソース別・原本形式でフィルタ
    ↓
personal/<日付>/<担当者>_<ソース>.csv を Drive保存
    ↓
リクエストのステータスを「完了」に更新
```

## セットアップ

### 1. Apps Script（ボタン）
1. スプレッドシートの **拡張機能 → Apps Script** に `scripts/csv_request_button.gs` を貼り付け・保存
2. 各「案件（◯◯さん）」シートで **挿入 → 図形** でボタン用の図形を置く
3. 図形の「⋮」→ **スクリプトを割り当て** に `requestCsv` と入力
4. （初回のみ）ボタンを押すと承認を求められるので許可

### 2. Mac側の監視（launchd）
```bash
cp /Users/mitomi/Claude/daily-report-automation/scripts/com.suprieve.csv-request-watcher.plist \
   ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.suprieve.csv-request-watcher.plist
launchctl list | grep csv-request-watcher
```
120秒おきに「CSV生成リクエスト」を確認し、pending依頼を処理する。

### 3. 動作確認
- 案件（◯◯さん）シートの I3:K3 に取得日を入れる
- 「CSVデータ作成」ボタンを押す
- 「CSV生成リクエスト」タブに行が追加され、数分後にステータスが「完了」になる
- Drive `personal/<日付>/` に `<担当者>_Yahoo.csv` `<担当者>_<ASP名>.csv` 等が保存される

## 手動実行（ボタンなしでも可）
```bash
cd /Users/mitomi/Claude/daily-report-automation
python -m phase2.build_personal_split            # 全担当者・シートの取得日範囲
python -m phase2.build_personal_split 2026-06-15 2026-06-18
python -m phase2.request_watcher                 # pending依頼を1回処理
```

## 注意
- Macが起動している必要がある（launchdのため）
- `.env` と `credentials/token.json` がローカルにあること
- ステータスが「エラー」の場合は同タブの「結果」列にメッセージが出る
