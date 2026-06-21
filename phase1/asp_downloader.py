import os
import glob
import re
import tempfile
import logging
import time
import requests
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from playwright.sync_api import sync_playwright, Page
from dotenv import load_dotenv
import yaml

load_dotenv()
logger = logging.getLogger(__name__)


class AspDownloader:
    def __init__(self, config_path: str = "config/asp_sites.yaml"):
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        self.sites = raw["asp_sites"]
        self.download_dir = tempfile.mkdtemp()

    def _find_downloaded_csv(self, pattern: str) -> str:
        """ダウンロードディレクトリからパターンに一致する最新CSVを返す"""
        matches = glob.glob(os.path.join(self.download_dir, pattern))
        if not matches:
            raise FileNotFoundError(f"CSVが見つかりません: {pattern} in {self.download_dir}")
        return sorted(matches)[-1]

    def _download_rentracks(self, page: Page, site: dict, date_str: str) -> None:
        """RENTRACKSの注文リストCSVをダウンロードする"""
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        report_date = (date.today() - timedelta(days=1)).strftime("%Y%m%d")

        # ログイン
        page.goto("https://manage.rentracks.jp/manage/top", wait_until="networkidle")
        page.fill('input[name="idMailaddress"]', username)
        page.fill('input[name="idLoginPassword"]', password)
        page.click('input[name="idButton"]')
        page.wait_for_load_state("networkidle")

        # 注文リストページへ
        page.goto("https://manage.rentracks.jp/manage/detail_sales", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # 発生日で昨日を選択して再表示
        page.select_option('select[name="idTermType"]', "0")   # 発生日
        page.select_option('select[name="idTermSelect"]', report_date)
        page.click('input[name="idButton1"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # CSVダウンロード
        with page.expect_download() as download_info:
            page.click('input[name="idButtonFD"]')
        download = download_info.value
        dest = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(dest)
        logger.info(f"RENTRACKS 注文リストCSVダウンロード完了: {dest}")

    def _download_felmat(self, page: Page, site: dict, date_str: str) -> None:
        """FELMATの成果発生CSVをダウンロードする"""
        url = os.path.expandvars(site["url"])
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        report_date = (date.today() - timedelta(days=1)).strftime("%Y/%m/%d")

        # ログイン
        page.goto(url)
        page.wait_for_load_state("networkidle")
        page.fill('#p_username', username)
        page.fill('#p_password', password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # 成果発生ページへ
        page.goto("https://www.felmat.net/publisher/conversion")
        page.wait_for_load_state("networkidle")

        # JavaScriptで日付をセット（datepickerを回避）
        page.evaluate(f"""
            let inputs = document.querySelectorAll('input[name="start_date"]');
            if(inputs.length > 0) inputs[0].value = '{report_date}';
            let inputs2 = document.querySelectorAll('input[name="end_date"]');
            if(inputs2.length > 0) inputs2[0].value = '{report_date}';
        """)
        page.wait_for_timeout(300)

        # CSVダウンロード
        with page.expect_download() as download_info:
            page.evaluate("document.querySelector('button[name=\"csv_dl\"]').click()")
        download = download_info.value
        dest = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(dest)
        logger.info(f"FELMAT 成果発生CSVダウンロード完了: {dest}")

    def _download_affiliateb(self, page: Page, site: dict, date_str: str) -> None:
        """afb（アフィリエイトb）の成果状況確認CSVをダウンロードする"""
        url = os.path.expandvars(site["url"])
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        report_date = (date.today() - timedelta(days=1)).strftime("%Y/%m/%d")

        # ログイン
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.fill('#formPartnerId', username)
        page.fill('#formPartnerPassword', password)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # 成果状況確認ページへ
        page.goto("https://www.afi-b.com/pa/result/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # 成果状況確認フォームに日付をセット
        result_form = 'form[action*="result"]'
        page.locator(f'{result_form} input[name="start_date"]').fill(report_date)
        page.locator(f'{result_form} input[name="end_date"]').fill(report_date)
        page.wait_for_timeout(300)

        # CSVダウンロード
        with page.expect_download() as download_info:
            page.locator(f'{result_form} input[name="csv"]').first.click()
        download = download_info.value
        dest = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(dest)
        logger.info(f"afb 成果状況確認CSVダウンロード完了: {dest}")

    def _download_accesstrade(self, page: Page, site: dict, date_str: str) -> None:
        """AccessTradeの計測パラメータ（詳細版）CSVをダウンロードする"""
        url = os.path.expandvars(site["url"])
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        report_date = date.today() - timedelta(days=1)

        # ログイン
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.fill('input[name="userId"]', username)
        page.fill('input[name="userPass"]', password)
        page.locator('input[name="userPass"]').press("Enter")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)

        # 計測パラメータページへ
        page.goto(
            "https://member.accesstrade.net/atv3/report/measure.html",
            wait_until="networkidle",
        )
        page.wait_for_timeout(5000)

        # 昨日を選択して検索
        page.locator('a:has-text("昨日")').click()
        page.wait_for_timeout(300)
        page.locator('#search_btn').click()
        page.wait_for_timeout(3000)

        # セッションクッキーを取得してrequestsで詳細版CSVダウンロード
        cookies = {c['name']: c['value'] for c in page.context.cookies()}
        headers = {
            'Referer': 'https://member.accesstrade.net/atv3/report/measure.html',
        }
        r = requests.post(
            'https://member.accesstrade.net/atv3/report/measure/download.html',
            cookies=cookies,
            headers=headers,
            data={
                'allSiteSelect': 'true',
                'targetYearFrom': str(report_date.year),
                'targetMonthFrom': str(report_date.month),
                'targetDayFrom': str(report_date.day),
                'targetYearTo': str(report_date.year),
                'targetMonthTo': str(report_date.month),
                'targetDayTo': str(report_date.day),
                'downloadType': '1',  # 詳細版
                'download': 'true',
            },
        )
        r.raise_for_status()
        dest = os.path.join(self.download_dir, f"accesstrade_measure_{date_str}.csv")
        with open(dest, 'wb') as f:
            f.write(r.content)
        logger.info(f"AccessTrade 計測パラメータ詳細版CSVダウンロード完了: {dest}")

    def _login_a8net_requests(self, username: str, password: str) -> list[dict]:
        """requestsでA8.netにログインしてPlaywright用クッキーリストを返す"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        session.get("http://www.a8.net/")
        session.post(
            "https://media-console.a8.net/external-login",
            data={"login": username, "passwd": password, "login_as_btn": "", "moa": "/a8"},
            allow_redirects=True,
        )
        return [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
            for c in session.cookies
        ]

    def _download_a8net(self, page: Page, site: dict, date_str: str) -> None:
        """A8.netのパラメータ計測CSVをダウンロードする。
        ページはAPIで取得したデータをクライアントサイドでCSV化するため、
        page.route() でAPIリクエストをインターセプトして日付を昨日に書き換える。"""
        import json as _json
        report_date = date.today() - timedelta(days=1)
        yesterday_iso = report_date.strftime("%Y-%m-%d")

        def intercept_api(route):
            """データ取得APIの日付を昨日に固定する"""
            if "/api/v1/user/report/parameter" in route.request.url:
                route.continue_(
                    post_data=_json.dumps({
                        "date_condition": {
                            "start_date": yesterday_iso,
                            "end_date": yesterday_iso,
                        }
                    })
                )
            else:
                route.continue_()

        page.route("**", intercept_api)

        # requestsでログイン → クッキーをContextに設定済み（download()側でセット）
        page.goto("https://media-console.a8.net/report/parameter", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # CSVダウンロード（クライアントサイドがAPIレスポンスからblob生成）
        with page.expect_download() as download_info:
            page.locator('button:has-text("CSV")').click()
        download = download_info.value
        dest = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(dest)
        logger.info(f"A8.net パラメータ計測CSVダウンロード完了: {dest}")

    def _download_funny(self, page: Page, site: dict, date_str: str) -> None:
        """allmedia-platform (FUNNY) の獲得ログCSVをダウンロードする"""
        url = os.path.expandvars(site["url"])
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        report_date = date.today() - timedelta(days=1)
        y_str = report_date.strftime("%Y-%m-%d")

        # ログイン
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.fill('input[name="loginId"]', username)
        page.fill('input[name="password"]', password)
        page.locator('input[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # 獲得ログページへ
        page.goto(
            "https://afad.allmedia-platform.com/partneradmin/report/action/log/list",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(3000)

        # 検索フォームはBootstrap collapseで非表示のためJS経由で操作
        page.evaluate("document.getElementById('yesterday').click()")
        page.wait_for_timeout(300)
        page.evaluate("document.querySelector('form[action*=\"log/list\"]').submit()")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # CSVフォームの値を取得してrequestsでPOST（セッションクッキーを使用）
        cookies_list = page.context.cookies()
        cookies = {c["name"]: c["value"] for c in cookies_list}
        form_data = page.evaluate("""() => {
            const form = document.querySelector('form[action*="log/list/csv"]');
            const inputs = form.querySelectorAll('input, select');
            return Object.fromEntries(Array.from(inputs).map(i => [i.name, i.value]));
        }""")
        r = requests.post(
            "https://afad.allmedia-platform.com/partneradmin/report/action/log/list/csv",
            data=form_data,
            cookies=cookies,
            headers={
                "Referer": "https://afad.allmedia-platform.com/partneradmin/report/action/log/list",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Origin": "https://afad.allmedia-platform.com",
            },
        )
        r.raise_for_status()
        dest = os.path.join(self.download_dir, f"funny_{y_str}.csv")
        with open(dest, "wb") as f:
            f.write(r.content)
        logger.info(f"FUNNY 獲得ログCSVダウンロード完了: {dest}")

    def _filter_csv_by_date(self, src_path: str, date_col: str, target_date: date,
                            encoding: str = "shift_jis") -> str:
        """CSVを指定日付カラムでフィルタし、昨日のデータのみの新CSVを返す。
        アフィリコード系システムは全件エクスポートのため必須。"""
        import pandas as pd
        target_str = target_date.strftime("%Y/%m/%d")
        df = pd.read_csv(src_path, encoding=encoding)
        if date_col not in df.columns:
            logger.warning(f"日付カラム '{date_col}' が見つかりません。元ファイルをそのまま返します。")
            return src_path
        filtered = df[df[date_col].astype(str).str.startswith(target_str)]
        logger.info(f"日付フィルタ: {len(df)}件 → {len(filtered)}件 ({target_str})")
        filtered_path = src_path.replace(".csv", f"_filtered_{target_str.replace('/', '')}.csv")
        filtered.to_csv(filtered_path, index=False, encoding=encoding)
        return filtered_path

    def _download_invahamo(self, page: Page, site: dict, date_str: str) -> None:
        """INVAHAMO は現在使用しない（INVGOLDと統合済み）"""
        logger.info("INVAHAMO はスキップします（INVGOLDと統合済みのため使用しない）")

    def _download_invgold(self, page: Page, site: dict, date_str: str) -> None:
        """アフィリコード (INVGOLD) の成果管理CSVをダウンロードする。
        発生日「昨日」で検索後、結果ページの「検索結果をCSVダウンロード」リンクをクリックする。"""
        url = os.path.expandvars(site["url"])
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])

        # ログイン
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.fill('input[name="mail"]', username)
        page.fill('input[name="pass"]', password)
        page.locator('button[type="submit"], input[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # 成果管理ページへ遷移し、発生日「昨日」ラジオを選択して検索
        page.goto("https://i-aff.com/search.php?type=action_log_raw", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.locator('input[name="regist_unix_type"][value="-1d"]').click()
        page.wait_for_timeout(300)
        page.locator('input[value="検索する"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # 検索結果ページの「検索結果をCSVダウンロード」リンクをクリック
        # ThickBox（iframe）でエクスポート選択ページが開く
        page.locator('a:has-text("検索結果をCSVダウンロード")').click()
        page.wait_for_timeout(3000)

        # iframe 内のエクスポートフォームを操作
        export_frame = next(
            f for f in page.frames if "action_log_rawExport" in f.url
        )
        export_frame.locator('input[name="csv_encoding"][value="SJIS-win"]').click()
        page.wait_for_timeout(200)
        with page.expect_download() as download_info:
            export_frame.locator('input[type="submit"]').click()
        download = download_info.value
        dest = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(dest)
        logger.info(f"INVGOLD 成果管理CSVダウンロード完了: {dest}")

    def _download_linkshare(self, page: Page, site: dict, date_str: str) -> None:
        """TGアフィリエイト (LINKSHARE) の成果別レポートCSVをAPI経由でダウンロードする"""
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        report_date = date.today() - timedelta(days=1)
        y_str = report_date.strftime("%Y-%m-%d")

        captured: dict = {"token": None, "affiliate_id": None}

        def on_request(request):
            if "api.trafficgate.net" in request.url and not captured["token"]:
                auth = request.headers.get("authorization", "")
                if auth:
                    captured["token"] = auth.replace("Bearer ", "")
            m = re.search(r"/affiliates/(\d+)", request.url)
            if m and not captured["affiliate_id"]:
                captured["affiliate_id"] = m.group(1)

        page.on("request", on_request)

        # ログイン → APIトークンとaffiliate_idを捕捉
        page.goto(os.path.expandvars(site["url"]), wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.fill("#username", username)
        page.fill("#password", password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(5000)

        # 成果別レポートページへ遷移してaffiliate_idを確定
        page.goto("https://www.trafficgate.net/affiliate/transactions", wait_until="networkidle")
        page.wait_for_timeout(3000)

        if not captured["token"] or not captured["affiliate_id"]:
            raise RuntimeError("LINKSHARE: トークンまたはaffiliate_id取得失敗")

        # Accept: text/csv でCSVを直接取得
        r = requests.get(
            f"https://api.trafficgate.net/v1/affiliates/{captured['affiliate_id']}/transactions",
            params={
                "start_date": f"{y_str} 00:00:00",
                "end_date": f"{y_str} 23:59:59",
                "per_page": 1000,
            },
            headers={
                "Authorization": f"Bearer {captured['token']}",
                "Accept": "text/csv",
            },
        )
        r.raise_for_status()
        dest = os.path.join(self.download_dir, f"linkshare_{y_str}.csv")
        with open(dest, "wb") as f:
            f.write(r.content)
        logger.info(f"LINKSHARE 成果別レポートCSVダウンロード完了: {dest}")

    def _download_sonic(self, page: Page, site: dict, date_str: str) -> str:
        """SS Affiliate (SONIC) の成果管理CSVをダウンロードする。
        アフィリコードと同一システム。全件エクスポート仕様のため発生日時でフィルタする。"""
        from urllib.parse import urlparse, parse_qs, quote
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])

        # ログイン
        login_url = "https://ads.sonicsense.jp/contents.php?c=user_login"
        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.fill('input[name="mail"]', username)
        page.fill('input[name="pass"]', password)
        page.click('input[type="submit"]')
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # 成果管理ページへ遷移し、発生日「昨日」ラジオを選択してフォーム送信
        page.goto("https://ads.sonicsense.jp/search.php?type=action_log_raw", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.locator('input[name="regist_unix_type"][value="-1d"]').click()
        page.wait_for_timeout(300)
        page.locator('input[type="submit"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # 結果URLから日付パラメータを取得してエクスポートURLを構築
        params = parse_qs(urlparse(page.url).query)
        regist_a = params.get("regist_unix_A", [""])[0]
        regist_b = params.get("regist_unix_B", [""])[0]
        export_url = (
            f"https://ads.sonicsense.jp/page.php?p=action_log_rawExport"
            f"&regist_unix_A={quote(regist_a)}&regist_unix_B={quote(regist_b)}"
            f"&regist_unix_type=-1d&tab_type=3&TB_iframe=true&height=240&width=730"
        )
        page.goto(export_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Shift-JISを選択してCSVダウンロード
        with page.expect_download() as download_info:
            page.evaluate("""() => {
                let form = document.querySelector('form');
                let radios = form.querySelectorAll('input[type=radio]');
                if (radios.length > 0) radios[0].click(); // Shift-JIS
                form.submit();
            }""")
        download = download_info.value
        dest = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(dest)
        logger.info(f"SONIC 成果管理CSV(全件)ダウンロード完了: {dest}")

        # システム仕様で全未確定成果が返るため昨日のみにフィルタ
        report_date = date.today() - timedelta(days=1)
        filtered = self._filter_csv_by_date(dest, "発生日時", report_date, encoding="shift_jis")
        logger.info(f"SONIC 日付フィルタ済みCSV: {filtered}")
        return filtered

    def _download_resultplus2(self, page: Page, site: dict, date_str: str) -> None:
        """ResultPlus2 (FUKUROシステム) のレポート>獲得ログCSVをダウンロードする"""
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        yesterday = date.today() - timedelta(days=1)
        y_str = yesterday.strftime("%Y-%m-%d")

        # ログイン
        page.goto(os.path.expandvars(site["url"]), wait_until="networkidle")
        page.wait_for_timeout(3000)
        page.locator('input[placeholder="ログインID"]').fill(username)
        page.locator('input[placeholder="パスワード"]').fill(password)
        page.locator('button:has-text("ログイン")').first.click()
        page.wait_for_timeout(5000)

        # Vue Router で獲得ログページへ
        page.evaluate("""() => {
            const app = document.querySelector('#app')?.__vue_app__;
            app.config.globalProperties.$router.push('/report/log');
        }""")
        page.wait_for_timeout(3000)

        # 日付を昨日にセット
        page.fill('input[placeholder="開始日"]', y_str)
        page.fill('input[placeholder="終了日"]', y_str)
        page.wait_for_timeout(300)
        page.locator('button:has-text("検索")').click()
        page.wait_for_timeout(3000)

        # CSVダウンロード
        with page.expect_download() as download_info:
            page.locator('button:has-text("CSVダウンロード")').click()
        download = download_info.value
        dest = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(dest)
        logger.info(f"RESULTPLUS2 獲得ログCSVダウンロード完了: {dest}")

    def _download_fukuro(self, page: Page, site: dict, date_str: str) -> None:
        """Circuit X (FUKURO) のリファラーレポートCSVをダウンロードする。
        AWS WAF対策のため channel='chrome' で起動したブラウザが必要。"""
        username = os.path.expandvars(site["username"])
        password = os.path.expandvars(site["password"])
        yesterday = date.today() - timedelta(days=1)

        # ログイン（WAF対策: channel='chrome' が download() 側でセット済み）
        page.goto(os.path.expandvars(site["url"]), wait_until="networkidle")
        page.wait_for_timeout(3000)
        page.fill('input[name="mail"]', username)
        page.wait_for_timeout(300)
        page.fill('input[name="password"]', password)
        page.wait_for_timeout(300)
        page.locator('button:has-text("ログイン")').click()
        page.wait_for_timeout(5000)

        # リファラーレポートページへ
        page.goto(
            "https://x-dashboard.cir.io/v2/general/media/reports/referrer",
            wait_until="networkidle",
        )
        page.wait_for_timeout(5000)

        # 日付ピッカーを開く
        page.locator('button#media-referrer-report-date-range').click()
        page.wait_for_timeout(1000)

        # 昨日の aria-label は例: "Sun Jun 07 2026"
        aria_label = yesterday.strftime('%a %b %d %Y')
        day_btn = page.locator(f'button[aria-label="{aria_label}"]')

        # カレンダーが昨日の月を表示していない場合は前月ボタンをクリック
        if day_btn.count() == 0:
            page.locator('button[aria-label="Go back 1 month"]').click()
            page.wait_for_timeout(500)

        # 昨日の日付ボタンをクリック（開始日）
        page.locator(f'button[aria-label="{aria_label}"]').click()
        page.wait_for_timeout(300)
        # 同じ日を再クリック（終了日）
        page.locator(f'button[aria-label="{aria_label}"]').click()
        page.wait_for_timeout(500)

        # 検索ボタンをクリック
        page.locator('button:has-text("検索")').click()
        page.wait_for_timeout(5000)

        # CSVダウンロード
        with page.expect_download() as download_info:
            page.locator('button:has-text("CSVダウンロード")').click()
        download = download_info.value
        dest = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(dest)
        logger.info(f"FUKURO リファラーCSVダウンロード完了: {dest}")

    def download(self, asp_name: str) -> str | None:
        """指定ASPからCSVをダウンロードしてローカルパスを返す。スキップASPはNoneを返す。"""
        site = self.sites[asp_name]
        asp_type = site.get("type", "")
        pattern = site["csv_filename_pattern"]
        date_str = (date.today() - timedelta(days=1)).isoformat()

        if asp_type == "invahamo":
            self._download_invahamo(None, site, date_str)
            return None

        with sync_playwright() as p:
            # FUKUROはAWS WAF対策でreal Chromeが必要
            if asp_type == "fukuro":
                browser = p.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                )
            else:
                browser = p.chromium.launch(headless=True)

            context = browser.new_context(
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )

            # A8.netはrequestsでログインしてクッキーをcontextに注入
            if asp_type == "a8net":
                username = os.path.expandvars(site["username"])
                password = os.path.expandvars(site["password"])
                cookies = self._login_a8net_requests(username, password)
                context.add_cookies(cookies)

            page = context.new_page()
            if asp_type == "fukuro":
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

            if asp_type == "felmat":
                self._download_felmat(page, site, date_str)
            elif asp_type == "rentracks":
                self._download_rentracks(page, site, date_str)
            elif asp_type == "affiliateb":
                self._download_affiliateb(page, site, date_str)
            elif asp_type == "accesstrade":
                self._download_accesstrade(page, site, date_str)
            elif asp_type == "a8net":
                self._download_a8net(page, site, date_str)
            elif asp_type == "funny":
                self._download_funny(page, site, date_str)
            elif asp_type == "invahamo":
                self._download_invahamo(page, site, date_str)
            elif asp_type == "invgold":
                self._download_invgold(page, site, date_str)
            elif asp_type == "linkshare":
                self._download_linkshare(page, site, date_str)
            elif asp_type == "fukuro":
                self._download_fukuro(page, site, date_str)
            elif asp_type == "sonic":
                self._download_sonic(page, site, date_str)
            elif asp_type == "resultplus2":
                self._download_resultplus2(page, site, date_str)
            else:
                raise NotImplementedError(f"未対応のASPタイプ: {asp_type}")

            browser.close()

        return self._find_downloaded_csv(pattern)

    def download_all(self, asp_names: list[str] | None = None) -> dict[str, str]:
        """複数ASPをまとめてダウンロードし、{asp_name: local_path} を返す"""
        targets = asp_names or list(self.sites.keys())
        results = {}
        for name in targets:
            try:
                path = self.download(name)
                if path is None:
                    logger.info(f"{name}: スキップ")
                    continue
                results[name] = path
                logger.info(f"{name}: ダウンロード完了 → {path}")
            except Exception as e:
                logger.error(f"{name}: ダウンロード失敗 → {e}")
        return results


def main():
    from phase1.drive_uploader import DriveUploader

    logging.basicConfig(level=logging.INFO)
    date_str = (date.today() - timedelta(days=1)).isoformat()
    downloader = AspDownloader()
    uploader = DriveUploader()

    # FELMATのみ（動作確認済み）
    for asp_name in ["felmat_f", "felmat_m"]:
        try:
            local_path = downloader.download(asp_name)
            site = downloader.sites[asp_name]
            output_filename = site.get("output_filename", f"{asp_name}.csv")
            file_id = uploader.upload_csv(local_path, output_filename, date_str)
            print(f"{output_filename} アップロード完了: {file_id}")
        except Exception as e:
            print(f"{asp_name} 失敗: {e}")


if __name__ == "__main__":
    main()
