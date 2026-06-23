/**
 * google_ads_export.gs
 * --------------------------------------------------------------
 * 4つのMCCそれぞれに設置するGoogle Ads Script。
 * 各MCCは配下の広告アカウントを巡回し、前日の広告グループ単位レポートを
 * 「自分専用のタブ」(google_ads_<MCC ID>) に書き出す。
 *
 * 同一の広告アカウントが複数MCCに紐づく場合は重複が出るが、
 * Python側 (phase1/google_ads_fetcher.py) で全タブを結合し重複削除する。
 *
 * 取得項目はYahoo広告フェッチャーと統一:
 *   date, account_id, account_name, campaign_id, campaign_name,
 *   adgroup_id, adgroup_name, impressions, clicks, cost, conversions
 *
 * セットアップ（4つのMCCそれぞれで実施）:
 *   1. 出力先の空スプレッドシートを作成し、URLを SHEET_URL に設定（4MCC共通の1シート）
 *   2. 各MCCの「一括操作 → スクリプト」に本ファイルを貼り付け
 *   3. 承認・プレビュー実行で google_ads_<MCC ID> タブへの出力を確認
 *   4. 毎朝のスケジュール実行を設定（4MCCすべて）
 */

// ▼▼▼ 設定 ▼▼▼
var SHEET_URL = 'ここに出力先スプレッドシートのURLを貼り付け';
// タブ名は実行中のMCC IDから自動決定（google_ads_<MCC ID>）。
// 手動で固定したい場合のみ TAB_NAME_OVERRIDE に値を設定する。
var TAB_NAME_OVERRIDE = '';
// ▲▲▲ 設定 ▲▲▲

var HEADER = [
  'date', 'account_id', 'account_name', 'campaign_id', 'campaign_name',
  'adgroup_id', 'adgroup_name', 'impressions', 'clicks', 'cost', 'conversions'
];

var GAQL =
  'SELECT segments.date, customer.id, customer.descriptive_name, ' +
  'campaign.id, campaign.name, ad_group.id, ad_group.name, ' +
  'metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions ' +
  'FROM ad_group WHERE segments.date DURING YESTERDAY ' +
  'AND metrics.impressions > 0';

function main() {
  // 実行中のMCC IDからタブ名を決定（select前に取得する）
  var mccId = AdsApp.currentAccount().getCustomerId().replace(/-/g, '');
  var tabName = TAB_NAME_OVERRIDE || ('google_ads_' + mccId);

  var rows = [];
  var accountIterator = AdsManagerApp.accounts().get();

  while (accountIterator.hasNext()) {
    var account = accountIterator.next();
    AdsManagerApp.select(account);
    try {
      collectAccount(account, rows);
    } catch (e) {
      Logger.log('アカウント取得失敗・スキップ: ' + account.getCustomerId() + ' / ' + e);
    }
  }

  writeToSheet(tabName, rows);
  Logger.log('完了: ' + rows.length + '行を ' + tabName + ' へ書き込みました');
}

function collectAccount(account, rows) {
  var accountId = account.getCustomerId();
  var accountName = account.getName() || '';

  var report = AdsApp.report(GAQL);
  var iterator = report.rows();
  while (iterator.hasNext()) {
    var row = iterator.next();
    var costMicros = parseFloat(row['metrics.cost_micros'] || 0);
    rows.push([
      row['segments.date'],
      accountId,
      accountName,
      row['campaign.id'],
      row['campaign.name'],
      row['ad_group.id'],
      row['ad_group.name'],
      row['metrics.impressions'],
      row['metrics.clicks'],
      Math.round(costMicros / 1000000),
      row['metrics.conversions']
    ]);
  }
}

function writeToSheet(tabName, rows) {
  var ss = SpreadsheetApp.openByUrl(SHEET_URL);
  var sheet = ss.getSheetByName(tabName);
  if (!sheet) {
    sheet = ss.insertSheet(tabName);
  }
  sheet.clear();
  sheet.getRange(1, 1, 1, HEADER.length).setValues([HEADER]);
  if (rows.length > 0) {
    sheet.getRange(2, 1, rows.length, HEADER.length).setValues(rows);
  }
}
