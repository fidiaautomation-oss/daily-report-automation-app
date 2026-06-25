/**
 * csv_request_button.gs
 * --------------------------------------------------------------
 * 案件管理スプレッドシートに紐づける Apps Script。
 * 各「案件（◯◯さん）」シートに置いた「CSVデータ作成」ボタンから呼ぶ。
 *
 * 押すと「CSV生成リクエスト」タブに依頼行(pending)を追記する。
 * Mac側のPython監視(phase2.request_watcher)が検知してCSVを生成し、
 * ステータスを「完了」に更新する。
 *
 * セットアップ:
 *   1. スプレッドシートの 拡張機能 → Apps Script に本ファイルを貼り付け
 *   2. 各「案件（◯◯さん）」シートに図形を挿入し「スクリプトを割り当て」で
 *      requestCsv を指定（これが「CSVデータ作成」ボタンになる）
 */

var REQUEST_TAB = 'CSV生成リクエスト';
var REQUEST_HEADER = ['日時', '担当者', '開始日', '終了日', 'ステータス', '結果'];
var CASE_TAB_RE = /^案件（(.+)）$/;

function requestCsv() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getActiveSheet();
  var title = sheet.getName();
  var m = title.match(CASE_TAB_RE);
  if (!m) {
    SpreadsheetApp.getUi().alert('「案件（担当者名）」シートで実行してください。');
    return;
  }
  var person = m[1];

  // 取得日（I3=開始 / K3=終了）
  var start = formatDate_(sheet.getRange('I3').getValue());
  var end = formatDate_(sheet.getRange('K3').getValue());

  var reqSheet = ss.getSheetByName(REQUEST_TAB);
  if (!reqSheet) {
    reqSheet = ss.insertSheet(REQUEST_TAB);
    reqSheet.getRange(1, 1, 1, REQUEST_HEADER.length).setValues([REQUEST_HEADER]);
  }
  var now = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm:ss');
  reqSheet.appendRow([now, person, start, end, 'pending', '']);

  SpreadsheetApp.getActiveSpreadsheet().toast(
    person + ' の CSV生成を依頼しました（' + start + '〜' + end + '）。数分後に完了します。',
    'CSV生成リクエスト', 5
  );
}

function formatDate_(v) {
  if (v instanceof Date) {
    return Utilities.formatDate(v, 'Asia/Tokyo', 'yyyy/MM/dd');
  }
  return String(v).trim();
}
