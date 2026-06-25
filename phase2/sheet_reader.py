"""案件管理シートの読み書き。

【運用チーム】案件管理シートから運用者ごとの担当案件・広告ID設定を読み込み、
マスタタブ（案件名マスタ・サイトマスタ・広告マスタ）の自動更新と、
入力欄の連動プルダウン・自動反映数式の設定を行う。

タブ命名規則:
    案件（<運用者名>）                 … ASP案件リスト
    配信プラットフォーム（<運用者名>）  … 広告媒体のキャンペーン/広告グループ
    入力候補（<運用者名>）             … 連動プルダウン用ヘルパー（自動生成）

案件タブの列:  B=No. / C=ASP名 / D=案件名 / E=プロモーションID（自動）
              / F=サイト名 / G=サイトID（自動）
配信PFタブの列: C=No. / D=配信プラットフォーム / E=キャンペーン名
              / F=取得単位 / G=キャンペーンor広告グループID（自動）
"""

import json
import os
import re
import logging

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

CASE_TAB_RE = re.compile(r"^案件（(.+)）$")
PLATFORM_TAB_RE = re.compile(r"^配信プラットフォーム（(.+)）$")
MASTER_TAB = "案件名マスタ"
SITE_MASTER_TAB = "サイトマスタ"
AD_MASTER_TAB = "広告マスタ"
HELPER_TAB_PREFIX = "入力候補"

# 入力支援を設定するデータ行数（3行目〜）
INPUT_ROWS = 50
DATA_START_ROW = 3  # 1始まり


class SheetReader:
    def __init__(self, spreadsheet_id: str = None):
        self.spreadsheet_id = spreadsheet_id or os.environ["ASSIGNMENT_SPREADSHEET_ID"]
        creds = self._load_credentials()
        self.service = build("sheets", "v4", credentials=creds)

    def _load_credentials(self) -> Credentials:
        token_json = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON")
        if token_json:
            info = json.loads(token_json)
        else:
            token_path = os.environ.get("GOOGLE_TOKEN_PATH", "credentials/token.json")
            with open(token_path) as f:
                info = json.load(f)
        creds = Credentials(
            token=info.get("token"),
            refresh_token=info.get("refresh_token"),
            token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=info.get("client_id"),
            client_secret=info.get("client_secret"),
            scopes=info.get("scopes"),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    # ── 基本操作 ────────────────────────────────────────────
    def _list_tabs(self) -> list:
        meta = self.service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id,
            fields="sheets.properties(sheetId,title)",
        ).execute()
        return [s["properties"] for s in meta["sheets"]]

    def _get_values(self, range_a1: str) -> list:
        res = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=range_a1
        ).execute()
        return res.get("values", [])

    def _ensure_tab(self, title: str, tabs: dict = None) -> int:
        """タブが無ければ作成し、sheetIdを返す。"""
        if tabs is None:
            tabs = {t["title"]: t["sheetId"] for t in self._list_tabs()}
        if title in tabs:
            return tabs[title]
        res = self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ).execute()
        sheet_id = res["replies"][0]["addSheet"]["properties"]["sheetId"]
        logger.info(f"タブ '{title}' を新規作成しました")
        return sheet_id

    def _replace_values(self, tab: str, values: list, clear_range: str = "A:Z") -> None:
        self.service.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id, range=f"'{tab}'!{clear_range}"
        ).execute()
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{tab}'!A1",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

    @staticmethod
    def _find_header_row(rows: list, required: str) -> int | None:
        """required で始まるセルを含む行をヘッダー行として探す。"""
        for i, row in enumerate(rows):
            if any(str(c).startswith(required) for c in row):
                return i
        return None

    @staticmethod
    def _col_of(header: list, name: str) -> int | None:
        """ヘッダー行から列番号を探す（完全一致 → 前方一致）。"""
        for i, c in enumerate(header):
            if str(c) == name:
                return i
        for i, c in enumerate(header):
            if str(c).startswith(name):
                return i
        return None

    # ── 担当設定の読み込み ──────────────────────────────────
    # ── CSV生成リクエスト（ボタン連携） ────────────────────
    REQUEST_TAB = "CSV生成リクエスト"
    REQUEST_HEADER = ["日時", "担当者", "開始日", "終了日", "ステータス", "結果"]

    def read_pending_requests(self) -> list:
        """CSV生成リクエストタブから status='pending' の依頼を返す。

        戻り値: [{"row": シート行番号(1始まり), "person", "start", "end"}, ...]
        """
        tabs = {t["title"] for t in self._list_tabs()}
        if self.REQUEST_TAB not in tabs:
            return []
        rows = self._get_values(f"'{self.REQUEST_TAB}'!A1:F1000")
        if not rows:
            return []
        pending = []
        # 1行目はヘッダー想定。2行目以降を見る。
        for i, row in enumerate(rows[1:], start=2):
            def c(idx):
                return row[idx].strip() if idx < len(row) and row[idx] else ""
            status = c(4)
            if status.lower() != "pending":
                continue
            pending.append({
                "row": i,
                "person": c(1),
                "start": c(2),
                "end": c(3),
            })
        return pending

    def update_request_status(self, row: int, status: str, result: str = "") -> None:
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.REQUEST_TAB}'!E{row}:F{row}",
            valueInputOption="RAW",
            body={"values": [[status, result]]},
        ).execute()

    def ensure_request_tab(self) -> None:
        tabs = {t["title"]: t["sheetId"] for t in self._list_tabs()}
        if self.REQUEST_TAB in tabs:
            return
        self._ensure_tab(self.REQUEST_TAB, tabs)
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.REQUEST_TAB}'!A1",
            valueInputOption="RAW",
            body={"values": [self.REQUEST_HEADER]},
        ).execute()

    def get_fetch_date_range(self) -> tuple:
        """案件（◯◯さん）タブの I3（開始）・K3（終了）から取得日範囲を読む。

        最初に見つかった案件タブの I3:K3 を参照する。形式は YYYY/MM/DD。
        読めない場合は (None, None) を返す。最大14日にクランプする。
        """
        from datetime import date, timedelta

        case_tabs = [t["title"] for t in self._list_tabs() if CASE_TAB_RE.match(t["title"])]
        if not case_tabs:
            return None, None
        vals = self._get_values(f"'{case_tabs[0]}'!I3:K3")
        if not vals or not vals[0]:
            return None, None
        row = vals[0]

        def parse(s):
            s = str(s).strip().replace("-", "/")
            for fmt in ("%Y/%m/%d",):
                try:
                    y, m, d = [int(x) for x in s.split("/")]
                    return date(y, m, d)
                except (ValueError, TypeError):
                    return None

        start = parse(row[0]) if len(row) > 0 else None
        end = parse(row[2]) if len(row) > 2 else (start)
        if start is None and end is None:
            return None, None
        start = start or end
        end = end or start
        if start > end:
            start, end = end, start
        if (end - start).days > 13:
            start = end - timedelta(days=13)
        return start, end

    def read_assignments(self) -> dict:
        """全運用者の担当設定を読み込む。

        戻り値: {運用者名: {"cases": [{"asp_name", "case_name", "site_id"}],
                           "platforms": [{"platform", "unit", "id"}]}}
        """
        assignments = {}
        for tab in self._list_tabs():
            title = tab["title"]
            m = CASE_TAB_RE.match(title)
            if m:
                person = m.group(1)
                rows = self._get_values(f"'{title}'!A1:Z200")
                hi = self._find_header_row(rows, "ASP名")
                if hi is None:
                    logger.warning(f"タブ '{title}' にヘッダー行（ASP名）が見つかりません")
                    continue
                header = rows[hi]

                def cell(row, name):
                    idx = self._col_of(header, name)
                    return (row[idx].strip() if idx is not None and idx < len(row) else "")

                cases = []
                for row in rows[hi + 1:]:
                    asp, case = cell(row, "ASP名"), cell(row, "案件名")
                    if not asp or not case:
                        continue
                    cases.append({
                        "asp_name": asp,
                        "case_name": case,
                        "site_id": cell(row, "サイトID"),
                    })
                assignments.setdefault(person, {"cases": [], "platforms": []})["cases"] = cases
                continue

            m = PLATFORM_TAB_RE.match(title)
            if m:
                person = m.group(1)
                rows = self._get_values(f"'{title}'!A1:Z200")
                hi = self._find_header_row(rows, "配信プラットフォーム")
                if hi is None:
                    logger.warning(f"タブ '{title}' にヘッダー行が見つかりません")
                    continue
                header = rows[hi]

                def cell(row, name):
                    idx = self._col_of(header, name)
                    return (row[idx].strip() if idx is not None and idx < len(row) else "")

                platforms = []
                for row in rows[hi + 1:]:
                    platform = cell(row, "配信プラットフォーム")
                    pid = cell(row, "キャンペーンor広告グループID")
                    if not platform or not pid:
                        continue
                    platforms.append({
                        "platform": platform,
                        "unit": cell(row, "取得単位"),
                        "id": pid,
                    })
                assignments.setdefault(person, {"cases": [], "platforms": []})["platforms"] = platforms

        return assignments

    # ── マスタの自動更新 ────────────────────────────────────
    def update_masters(self, case_master: list, site_master: list, ad_master: list) -> None:
        """3つのマスタタブを最新CSVデータで更新する。空のマスタは更新しない。"""
        tabs = {t["title"]: t["sheetId"] for t in self._list_tabs()}

        if case_master:
            self._ensure_tab(MASTER_TAB, tabs)
            values = [["ASP名", "案件名", "プロモーションID"]] + [
                [c["asp_name"], c["case_name"], c.get("promo_id", "")]
                for c in case_master
            ]
            self._replace_values(MASTER_TAB, values)
            logger.info(f"案件名マスタを更新: {len(case_master)}件")
        else:
            logger.warning("ASPデータが0件のため案件名マスタの更新をスキップ")

        if site_master:
            self._ensure_tab(SITE_MASTER_TAB, tabs)
            values = [["ASP名", "案件名", "サイト名", "サイトID"]] + [
                [s["asp_name"], s["case_name"], s["site_name"], s["site_id"]]
                for s in site_master
            ]
            self._replace_values(SITE_MASTER_TAB, values)
            logger.info(f"サイトマスタを更新: {len(site_master)}件")

        if ad_master:
            self._ensure_tab(AD_MASTER_TAB, tabs)
            values = [["配信プラットフォーム", "取得単位", "名称", "ID"]] + [
                [a["platform"], a["unit"], a["name"], a["id"]] for a in ad_master
            ]
            self._replace_values(AD_MASTER_TAB, values)
            logger.info(f"広告マスタを更新: {len(ad_master)}件")

    # ── 入力支援（連動プルダウン＋自動反映数式）────────────
    def setup_input_helpers(self) -> None:
        """全運用者タブに連動プルダウンと自動反映数式を設定する（冪等）。

        運用者ごとにヘルパータブ『入力候補（◯◯さん）』を作り、行ごとの
        入力候補をFILTER数式で生成。各入力セルのデータ検証はヘルパー行を参照する。
        自動列（プロモーションID・サイトID・広告ID）にはXLOOKUP数式を設定する。
        """
        tabs = {t["title"]: t["sheetId"] for t in self._list_tabs()}
        persons = set()
        for title in tabs:
            for pat in (CASE_TAB_RE, PLATFORM_TAB_RE):
                m = pat.match(title)
                if m:
                    persons.add(m.group(1))

        for person in sorted(persons):
            helper_tab = f"{HELPER_TAB_PREFIX}（{person}）"
            helper_id = self._ensure_tab(helper_tab, tabs)
            case_tab = f"案件（{person}）"
            pf_tab = f"配信プラットフォーム（{person}）"

            helper_rows = []   # (行番号1始まり, 数式)
            formulas = []      # (タブ, セルA1, 数式)
            validations = []   # batchUpdate requests

            # --- 案件タブ: D=案件名プルダウン / E=プロモーションID自動
            #              F=サイト名プルダウン / G=サイトID自動
            if case_tab in tabs:
                for i in range(INPUT_ROWS):
                    r = DATA_START_ROW + i          # 案件タブのデータ行
                    h_case = 1 + i                  # ヘルパー: 案件名候補行
                    h_site = 1 + INPUT_ROWS + i     # ヘルパー: サイト名候補行
                    helper_rows.append((h_case, (
                        f"=IFERROR(TRANSPOSE(UNIQUE(FILTER('{MASTER_TAB}'!B:B,"
                        f"'{MASTER_TAB}'!A:A='{case_tab}'!C{r}))),\"\")"
                    )))
                    helper_rows.append((h_site, (
                        f"=IFERROR(TRANSPOSE(UNIQUE(FILTER('{SITE_MASTER_TAB}'!C:C,"
                        f"('{SITE_MASTER_TAB}'!A:A='{case_tab}'!C{r})*"
                        f"('{SITE_MASTER_TAB}'!B:B='{case_tab}'!D{r})))),\"\")"
                    )))
                    formulas.append((case_tab, f"E{r}", (
                        f"=IFERROR(XLOOKUP('{case_tab}'!C{r}&\"|\"&'{case_tab}'!D{r},"
                        f"ARRAYFORMULA('{MASTER_TAB}'!A:A&\"|\"&'{MASTER_TAB}'!B:B),"
                        f"'{MASTER_TAB}'!C:C),\"\")"
                    )))
                    formulas.append((case_tab, f"G{r}", (
                        f"=IFERROR(XLOOKUP('{case_tab}'!C{r}&\"|\"&'{case_tab}'!D{r}&\"|\"&'{case_tab}'!F{r},"
                        f"ARRAYFORMULA('{SITE_MASTER_TAB}'!A:A&\"|\"&'{SITE_MASTER_TAB}'!B:B&\"|\"&'{SITE_MASTER_TAB}'!C:C),"
                        f"'{SITE_MASTER_TAB}'!D:D),\"\")"
                    )))
                    # D列（案件名）の連動プルダウン
                    validations.append(self._validation_request(
                        tabs[case_tab], r, 3, helper_tab, h_case))
                    # F列（サイト名）の連動プルダウン
                    validations.append(self._validation_request(
                        tabs[case_tab], r, 5, helper_tab, h_site))

            # --- 配信PFタブ: E=キャンペーン名プルダウン / G=ID自動
            if pf_tab in tabs:
                for i in range(INPUT_ROWS):
                    r = DATA_START_ROW + i
                    h_ad = 1 + INPUT_ROWS * 2 + i   # ヘルパー: 広告名称候補行
                    helper_rows.append((h_ad, (
                        f"=IFERROR(TRANSPOSE(UNIQUE(FILTER('{AD_MASTER_TAB}'!C:C,"
                        f"('{AD_MASTER_TAB}'!A:A='{pf_tab}'!D{r})*"
                        f"(('{AD_MASTER_TAB}'!B:B='{pf_tab}'!F{r})+('{pf_tab}'!F{r}=\"\"))))),\"\")"
                    )))
                    formulas.append((pf_tab, f"G{r}", (
                        f"=IFERROR(XLOOKUP('{pf_tab}'!D{r}&\"|\"&'{pf_tab}'!F{r}&\"|\"&'{pf_tab}'!E{r},"
                        f"ARRAYFORMULA('{AD_MASTER_TAB}'!A:A&\"|\"&'{AD_MASTER_TAB}'!B:B&\"|\"&'{AD_MASTER_TAB}'!C:C),"
                        f"'{AD_MASTER_TAB}'!D:D),\"\")"
                    )))
                    # E列（キャンペーン名）の連動プルダウン
                    validations.append(self._validation_request(
                        tabs[pf_tab], r, 4, helper_tab, h_ad))

            # ヘルパータブへ数式書き込み（A列のみ。横に展開される）
            data = [
                {"range": f"'{helper_tab}'!A{row}", "values": [[formula]]}
                for row, formula in helper_rows
            ]
            data += [
                {"range": f"'{tab}'!{cell}", "values": [[formula]]}
                for tab, cell, formula in formulas
            ]
            if data:
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"valueInputOption": "USER_ENTERED", "data": data},
                ).execute()
            if validations:
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": validations},
                ).execute()
            logger.info(f"入力支援を設定: {person}（数式{len(data)}件 / 検証{len(validations)}件）")

    def _validation_request(self, sheet_id: int, row: int, col_idx: int,
                            helper_tab: str, helper_row: int) -> dict:
        """1セル分のデータ検証（ヘルパー行参照のプルダウン）リクエストを作る。"""
        return {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row - 1,
                    "endRowIndex": row,
                    "startColumnIndex": col_idx,
                    "endColumnIndex": col_idx + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_RANGE",
                        "values": [{
                            "userEnteredValue": f"='{helper_tab}'!${self._col_letter(0)}${helper_row}:$AZ${helper_row}"
                        }],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        }

    @staticmethod
    def _col_letter(idx: int) -> str:
        letters = ""
        idx += 1
        while idx:
            idx, rem = divmod(idx - 1, 26)
            letters = chr(65 + rem) + letters
        return letters
