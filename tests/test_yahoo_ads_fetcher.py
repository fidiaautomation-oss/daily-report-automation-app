import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("YAHOO_ADS_CLIENT_ID", "cid")
    monkeypatch.setenv("YAHOO_ADS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YAHOO_ADS_REFRESH_TOKENS", "rtoken1,rtoken2")


def test_get_access_token(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    mock_res = MagicMock()
    mock_res.json.return_value = {"access_token": "abc123", "expires_in": 3600}
    mock_res.raise_for_status.return_value = None

    with patch("phase1.yahoo_ads_fetcher.requests.post", return_value=mock_res) as mp:
        token = fetcher._get_access_token("rtoken1")

    assert token == "abc123"
    args, kwargs = mp.call_args
    assert "biz-oauth.yahoo.co.jp" in args[0]
    assert kwargs["data"]["grant_type"] == "refresh_token"
    assert kwargs["data"]["refresh_token"] == "rtoken1"


def test_refresh_tokens_parsed(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    assert fetcher.refresh_tokens == ["rtoken1", "rtoken2"]


def test_no_refresh_tokens_raises(monkeypatch):
    monkeypatch.setenv("YAHOO_ADS_CLIENT_ID", "cid")
    monkeypatch.setenv("YAHOO_ADS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YAHOO_ADS_REFRESH_TOKENS", "")
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    with pytest.raises(ValueError):
        YahooAdsFetcher()


def _account_value(account_id, name, is_mcc="FALSE"):
    return {"account": {"accountId": account_id, "accountName": name, "isMccAccount": is_mcc}}


def test_discover_accounts_for_token_excludes_mcc(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()

    res = MagicMock()
    res.raise_for_status.return_value = None
    res.json.return_value = {
        "rval": {
            "totalNumEntries": 2,
            "values": [
                _account_value(111, "広告A"),
                _account_value(999, "MCC", is_mcc="TRUE"),
            ],
        }
    }

    with patch.object(fetcher, "_get_access_token", return_value="tok"), \
         patch("phase1.yahoo_ads_fetcher.requests.post", return_value=res):
        accounts = fetcher._discover_accounts_for_token("rtoken1")

    assert accounts == [{"account_id": "111", "account_name": "広告A"}]


def test_discover_accounts_dedupes_across_tokens(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()

    def per_token(rt):
        if rt == "rtoken1":
            return [{"account_id": "111", "account_name": "A"},
                    {"account_id": "222", "account_name": "B"}]
        return [{"account_id": "222", "account_name": "B"},
                {"account_id": "333", "account_name": "C"}]

    with patch.object(fetcher, "_discover_accounts_for_token", side_effect=per_token):
        discovered = fetcher.discover_accounts()

    ids = [d["account_id"] for d in discovered]
    assert ids == ["111", "222", "333"]
    # 222 は最初に見つかった rtoken1 に紐づく
    assert next(d for d in discovered if d["account_id"] == "222")["refresh_token"] == "rtoken1"


def test_create_report(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    fetcher._access_token = "tok"
    mock_res = MagicMock()
    mock_res.json.return_value = {
        "rval": {"values": [{"reportDefinition": {"reportJobId": 999}}]}
    }
    mock_res.raise_for_status.return_value = None

    with patch("phase1.yahoo_ads_fetcher.requests.post", return_value=mock_res) as mp:
        job_id = fetcher._create_report("111")

    assert job_id == 999
    args, kwargs = mp.call_args
    assert args[0].endswith("/add")
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["headers"]["x-z-base-account-id"] == "111"
    body = kwargs["json"]
    assert body["accountId"] == 111
    op = body["operand"][0]
    assert op["reportType"] == "ADGROUP"
    assert op["reportDateRangeType"] == "CUSTOM_DATE"
    assert op["reportDownloadFormat"] == "TSV"
    assert set(op["fields"]) == set(
        ["DAY", "CAMPAIGN_ID", "CAMPAIGN_NAME", "ADGROUP_ID", "ADGROUP_NAME", "IMPS", "CLICKS", "COST", "ALL_CONV"]
    )


def test_poll_report_completes(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    fetcher._access_token = "tok"

    def make_res(status):
        r = MagicMock()
        r.json.return_value = {
            "rval": {"values": [{"reportDefinition": {"reportJobStatus": status}}]}
        }
        r.raise_for_status.return_value = None
        return r

    responses = [make_res("WAIT"), make_res("COMPLETED")]
    with patch("phase1.yahoo_ads_fetcher.requests.post", side_effect=responses), \
         patch("phase1.yahoo_ads_fetcher.time.sleep"):
        ok = fetcher._poll_report("111", 999)

    assert ok is True


def test_poll_report_failed(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    fetcher._access_token = "tok"
    r = MagicMock()
    r.json.return_value = {
        "rval": {"values": [{"reportDefinition": {"reportJobStatus": "FAILED"}}]}
    }
    r.raise_for_status.return_value = None

    with patch("phase1.yahoo_ads_fetcher.requests.post", return_value=r), \
         patch("phase1.yahoo_ads_fetcher.time.sleep"):
        ok = fetcher._poll_report("111", 999)

    assert ok is False


def test_download_report(env):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    fetcher._access_token = "tok"

    # ダウンロードCSVは日本語ヘッダー。列順は REPORT_FIELDS 順。
    # 実データ行 + 合計行（日付空・全ゼロ）の2行構成を模す。
    tsv = (
        "日\tキャンペーンID\tキャンペーン名\t広告グループID\t広告グループ名\tインプレッション数\tクリック数\tコスト\tコンバージョン数（全て）\n"
        "2026-06-08\t777\tキャンペA\t888\tグループX\t100\t5\t1200\t2\n"
        "\t\t\t\t\t0\t0\t0\t0\n"
    )
    r = MagicMock()
    r.text = tsv
    r.content = tsv.encode("utf-8")
    r.raise_for_status.return_value = None

    with patch("phase1.yahoo_ads_fetcher.requests.post", return_value=r):
        df = fetcher._download_report("111", 999, "広告A")

    # 合計行は除去され、実データ1行のみ
    assert len(df) == 1
    assert df.iloc[0]["date"] == "2026-06-08"
    assert df.iloc[0]["campaign_name"] == "キャンペA"
    assert df.iloc[0]["impressions"] == "100"
    assert df.iloc[0]["conversions"] == "2"
    assert df.iloc[0]["account_id"] == "111"
    assert df.iloc[0]["account_name"] == "広告A"


def test_fetch_to_csv_combines_accounts(env, tmp_path):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()

    discovered = [
        {"account_id": "111", "account_name": "A", "refresh_token": "rtoken1"},
        {"account_id": "222", "account_name": "B", "refresh_token": "rtoken2"},
    ]

    def fake_df(account_id, job_id, account_name=""):
        return pd.DataFrame([{
            "date": "2026-06-07", "campaign_id": "777", "campaign_name": "C",
            "adgroup_id": "888", "adgroup_name": "G",
            "impressions": "10", "clicks": "1", "cost": "100",
            "conversions": "0", "account_id": account_id, "account_name": account_name,
        }])

    with patch.object(fetcher, "discover_accounts", return_value=discovered), \
         patch.object(fetcher, "_get_access_token", return_value="tok"), \
         patch.object(fetcher, "_create_report", return_value=999), \
         patch.object(fetcher, "_poll_report", return_value=True), \
         patch.object(fetcher, "_download_report", side_effect=fake_df):
        out = tmp_path / "yahoo_ads.csv"
        fetcher.fetch_to_csv(str(out))

    df = pd.read_csv(out, dtype=str)
    assert len(df) == 2
    assert set(df["account_id"]) == {"111", "222"}
    assert list(df.columns) == YahooAdsFetcher.OUTPUT_COLUMNS


def test_fetch_to_csv_skips_failed_account(env, tmp_path):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()

    discovered = [
        {"account_id": "111", "account_name": "A", "refresh_token": "rtoken1"},
        {"account_id": "222", "account_name": "B", "refresh_token": "rtoken2"},
    ]

    def fake_df(account_id, job_id, account_name=""):
        return pd.DataFrame([{
            "date": "2026-06-07", "campaign_id": "777", "campaign_name": "C",
            "adgroup_id": "888", "adgroup_name": "G",
            "impressions": "10", "clicks": "1", "cost": "100",
            "conversions": "0", "account_id": account_id, "account_name": account_name,
        }])

    poll_results = {"111": True, "222": False}

    with patch.object(fetcher, "discover_accounts", return_value=discovered), \
         patch.object(fetcher, "_get_access_token", return_value="tok"), \
         patch.object(fetcher, "_create_report", return_value=999), \
         patch.object(fetcher, "_poll_report", side_effect=lambda aid, jid: poll_results[aid]), \
         patch.object(fetcher, "_download_report", side_effect=fake_df):
        out = tmp_path / "yahoo_ads.csv"
        fetcher.fetch_to_csv(str(out))

    df = pd.read_csv(out, dtype=str)
    assert len(df) == 1
    assert set(df["account_id"]) == {"111"}


def test_fetch_to_csv_all_failed_writes_empty(env, tmp_path):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    discovered = [
        {"account_id": "111", "account_name": "A", "refresh_token": "rtoken1"},
    ]
    with patch.object(fetcher, "discover_accounts", return_value=discovered), \
         patch.object(fetcher, "_get_access_token", return_value="tok"), \
         patch.object(fetcher, "_create_report", return_value=999), \
         patch.object(fetcher, "_poll_report", return_value=False), \
         patch.object(fetcher, "_download_report", return_value=pd.DataFrame()):
        out = tmp_path / "yahoo_ads.csv"
        fetcher.fetch_to_csv(str(out))

    df = pd.read_csv(out, dtype=str)
    assert len(df) == 0
    assert list(df.columns) == YahooAdsFetcher.OUTPUT_COLUMNS


def test_write_accounts_to_env(env, tmp_path):
    from phase1.yahoo_ads_fetcher import YahooAdsFetcher

    fetcher = YahooAdsFetcher()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "YAHOO_ADS_CLIENT_ID=cid\nYAHOO_ADS_ACCOUNT_IDS=old1,old2\nOTHER=keep\n",
        encoding="utf-8",
    )

    discovered = [
        {"account_id": "111", "account_name": "A", "refresh_token": "rtoken1"},
        {"account_id": "222", "account_name": "B", "refresh_token": "rtoken2"},
    ]
    with patch.object(fetcher, "discover_accounts", return_value=discovered):
        fetcher.write_accounts_to_env(str(env_file))

    content = env_file.read_text(encoding="utf-8")
    assert "YAHOO_ADS_ACCOUNT_IDS=111,222" in content
    assert "old1,old2" not in content
    assert "OTHER=keep" in content
    assert "111: A" in content
    assert "222: B" in content
