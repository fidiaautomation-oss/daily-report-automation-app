/**
 * google_ads_export.gs
 * --------------------------------------------------------------
 * 最上位の自動化用MCCに設置するGoogle Ads Script。
 * 配下（ネストされたMCC配下を含む）の全広告アカウントを巡回し、
 * 前日の広告グループ単位レポートを出力先スプレッドシートに書き出す。
 *
 * 取得項目はYahoo広告フェッチャーと統一:
 *   date, account_id, account_name, campaign_id, campaign_name,
 *   adgroup_id, adgroup_name, impressions, clicks, cost, conversions
 *
 * セットアップ:
 *   1. 出力先の空スプレッドシートを作成し、URLを SHEET_URL に設定
 *   2. 最上位MCCの「一括操作 → スクリプト」に本ファイルを貼り付け
 *   3. 承認・プレビュー実行で google_ads シートへの出力を確認
 *   4. 毎朝のスケジュール実行を設定
 */

// ▼▼▼ 設定 ▼▼▼
var SHEET_URL = 'ここに出力先スプレッドシートのURLを貼り付け';
var SHEET_NAME = 'google_ads';
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

  writeToSheet(rows);
  Logger.log('完了: ' + rows.length + '行を ' + SHEET_NAME + ' へ書き込みました');
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

function writeToSheet(rows) {
  var ss = SpreadsheetApp.openByUrl(SHEET_URL);
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  sheet.clear();
  sheet.getRange(1, 1, 1, HEADER.length).setValues([HEADER]);
  if (rows.length > 0) {
    sheet.getRange(2, 1, rows.length, HEADER.length).setValues(rows);
  }
}
