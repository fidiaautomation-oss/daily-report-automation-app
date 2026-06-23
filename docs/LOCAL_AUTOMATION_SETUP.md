# ローカル毎朝自動化 セットアップ手順（ASP + Yahoo広告）

ASPスクレイピングとYahoo広告APIは、提供元がクラウド（海外データセンター）IPを
ブロック/403拒否するため、**Mac上で launchd により毎朝自動実行**する。
（Google広告はGitHub Actionsでクラウド実行済み）

---

## 構成

| ファイル | 役割 |
|----------|------|
| `phase1/run_local.py` | ASP全社＋Yahooを取得してDrive保存する統合ランナー |
| `scripts/run_local.sh` | launchdから呼ぶ起動スクリプト（conda pythonでrun_localを実行） |
| `scripts/com.suprieve.daily-report-local.plist` | launchd定義（毎朝7:00 JST） |

実行ログ：`logs/run_local_YYYY-MM-DD.log` と `logs/launchd.out/err.log`

---

## セットアップ手順

### 1. 手動で動作確認
```bash
cd /Users/mitomi/Claude/daily-report-automation
python -m phase1.run_local
```
`logs/run_local_<日付>.log` に各ASP・Yahooの成否が記録される。
Drive `raw/YYYY-MM-DD/` に各CSVが保存されればOK。

### 2. launchd に登録
```bash
# plistを LaunchAgents へコピー
cp /Users/mitomi/Claude/daily-report-automation/scripts/com.suprieve.daily-report-local.plist \
   ~/Library/LaunchAgents/

# 登録（macOS 13+ の推奨コマンド）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.suprieve.daily-report-local.plist

# 登録確認
launchctl list | grep daily-report-local
```

> 旧コマンドの場合は `launchctl load ~/Library/LaunchAgents/com.suprieve.daily-report-local.plist`

### 3. 即時テスト実行（スケジュールを待たずに動作確認）
```bash
launchctl kickstart -k gui/$(id -u)/com.suprieve.daily-report-local
# ログ確認
tail -f /Users/mitomi/Claude/daily-report-automation/logs/launchd.err.log
```

---

## 実行タイミング（全体像）

| 時刻(JST) | 処理 | 場所 |
|----------|------|------|
| 06:00-07:00 | Google Ads Script → スプレッドシート書込 | Google（自動） |
| **07:00** | **ASP + Yahoo → Drive保存** | **Mac launchd（本手順）** |
| 08:00 | Google広告 → Drive保存 | GitHub Actions |

→ 朝8時時点で `raw/YYYY-MM-DD/` にASP・Yahoo・Googleが揃う。

---

## 注意事項

- **Macが起動している必要がある**（スリープ中は実行されない）。
  - 対策：システム設定 → バッテリー/省エネで「スケジュール起動」を7:00前に設定するか、
    plistの `RunAtLoad` を活用（起動時に追いかけ実行）。
- **Playwrightのブラウザ**が必要（`playwright install chromium` 済みであること）。
  FUKUROは実Chrome（`channel=chrome`）を使うため、Google Chromeのインストールも必要。
- **認証情報**は `.env` と `credentials/token.json` をローカルに置いたまま使う（コミットしない）。
- 失敗時は `logs/run_local_<日付>.log` でASPごとのエラーを確認。

---

## 停止・再登録

```bash
# 停止
launchctl bootout gui/$(id -u)/com.suprieve.daily-report-local
# plist修正後に再登録
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.suprieve.daily-report-local.plist
```
