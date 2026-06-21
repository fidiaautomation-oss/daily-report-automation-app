import pandas as pd
import pytest

from phase2.personal_csv_builder import (
    PersonalCsvBuilder,
    DETAIL_COLUMNS,
    SUMMARY_COLUMNS,
)


@pytest.fixture
def builder():
    return PersonalCsvBuilder("config/normalize_mapping.yaml")


# ── 正規化 ──────────────────────────────────────────────────
def test_normalize_asp_felmat(builder):
    csv = (
        "成果番号,Click日時,発生日時,確定日時,プロモーションID,プロモーション,"
        "成果報酬（税抜）,サイトID,サイト\n"
        "1,2026-06-08 09:00,2026-06-08 10:00,,P1,テスト案件A,1000,S001,サイトX\n"
        "2,2026-06-08 11:00,2026-06-08 12:00,,P2,テスト案件B,\"2,000\",S002,サイトY\n"
    ).encode("shift_jis")
    df = builder.normalize_asp({"felmat_f.csv": csv})
    assert len(df) == 2
    assert df.iloc[0]["asp_name"] == "Felmat"
    assert df.iloc[0]["case_name"] == "テスト案件A"
    assert df.iloc[0]["site_id"] == "S001"
    assert df.iloc[0]["promo_id"] == "P1"
    assert df.iloc[0]["site_name"] == "サイトX"
    assert df.iloc[0]["reward"] == 1000
    assert df.iloc[1]["reward"] == 2000  # カンマ除去


def test_normalize_asp_missing_file_skipped(builder):
    df = builder.normalize_asp({})
    assert len(df) == 0
    assert set(df.columns) >= {"date", "asp_name", "case_name", "site_id", "reward", "promo_id", "site_name"}


def test_normalize_asp_empty_bytes_skipped(builder):
    df = builder.normalize_asp({"funny.csv": b""})
    assert len(df) == 0


def test_normalize_asp_reward_missing_column(builder):
    # RESULTPLUS2 は報酬額列なし → reward=0
    csv = (
        "承認日時,クリック日時,注文日時,広告名,パートナーサイト名\n"
        ",2026-06-08 09:00,2026-06-08 10:00,広告X,サイトZ\n"
    ).encode("utf-8-sig")
    df = builder.normalize_asp({"resultplus2.csv": csv})
    assert len(df) == 1
    assert df.iloc[0]["reward"] == 0
    assert df.iloc[0]["case_name"] == "広告X"


def test_normalize_google(builder):
    csv = (
        "date,account_id,account_name,campaign_id,campaign_name,"
        "adgroup_id,adgroup_name,impressions,clicks,cost,conversions\n"
        "2026-06-08,g1,テスト,555,GC1,666,GG1,200,10,2000,4\n"
    ).encode("utf-8-sig")
    df = builder.normalize_google({"google_ads.csv": csv})
    assert len(df) == 1
    assert df.iloc[0]["cost"] == 2000


def test_normalize_yahoo(builder):
    csv = (
        "date,account_id,account_name,campaign_id,campaign_name,"
        "adgroup_id,adgroup_name,impressions,clicks,cost,conversions\n"
        "2026-06-08,111,テスト,777,キャンペA,888,グループX,100,5,1200,2\n"
    ).encode("utf-8-sig")
    df = builder.normalize_yahoo({"yahoo_ads.csv": csv})
    assert len(df) == 1
    assert df.iloc[0]["cost"] == 1200


# ── 突合 ────────────────────────────────────────────────────
@pytest.fixture
def asp_df():
    return pd.DataFrame([
        {"date": "2026-06-08 10:00", "asp_name": "Felmat", "case_name": "案件A",
         "site_id": "S001", "reward": 1000},
        {"date": "2026-06-08 11:00", "asp_name": "Felmat", "case_name": "案件A",
         "site_id": "S002", "reward": 1500},
        {"date": "2026-06-08 12:00", "asp_name": "A8.net", "case_name": "案件B",
         "site_id": "", "reward": 500},
    ])


@pytest.fixture
def yahoo_df():
    return pd.DataFrame([
        {"date": "2026-06-08", "account_id": "1", "account_name": "acc",
         "campaign_id": "777", "campaign_name": "C1", "adgroup_id": "888",
         "adgroup_name": "G1", "impressions": 100, "clicks": 5, "cost": 1200,
         "conversions": 2},
        {"date": "2026-06-08", "account_id": "1", "account_name": "acc",
         "campaign_id": "777", "campaign_name": "C1", "adgroup_id": "889",
         "adgroup_name": "G2", "impressions": 50, "clicks": 2, "cost": 300,
         "conversions": 0},
    ])


def test_build_person_exact_match(builder, asp_df, yahoo_df):
    assignment = {
        "cases": [{"asp_name": "Felmat", "case_name": "案件A", "site_id": ""}],
        "platforms": [],
    }
    detail, summary = builder.build_person("井上さん", assignment, asp_df, yahoo_df)
    assert len(detail) == 2  # 案件Aの2行（site_id指定なし）
    assert list(detail.columns) == DETAIL_COLUMNS
    assert summary.iloc[0]["発生件数"] == 2
    assert summary.iloc[0]["報酬合計"] == 2500


def test_build_person_site_id_filter(builder, asp_df, yahoo_df):
    assignment = {
        "cases": [{"asp_name": "Felmat", "case_name": "案件A", "site_id": "S001"}],
        "platforms": [],
    }
    detail, summary = builder.build_person("井上さん", assignment, asp_df, yahoo_df)
    assert len(detail) == 1
    assert summary.iloc[0]["報酬合計"] == 1000


def test_build_person_no_partial_match(builder, asp_df, yahoo_df):
    # 完全一致のみ。「案件」では「案件A」にマッチしない
    assignment = {
        "cases": [{"asp_name": "Felmat", "case_name": "案件", "site_id": ""}],
        "platforms": [],
    }
    detail, summary = builder.build_person("井上さん", assignment, asp_df, yahoo_df)
    assert len(detail) == 0
    assert summary.iloc[0]["発生件数"] == 0  # 不一致でも集計に0行を出す


def test_build_person_yahoo_campaign(builder, asp_df, yahoo_df):
    assignment = {
        "cases": [],
        "platforms": [{"platform": "Yahoo", "unit": "キャンペーンID", "id": "777"}],
    }
    detail, summary = builder.build_person("井上さん", assignment, asp_df, yahoo_df)
    assert len(detail) == 2  # campaign 777 の2行
    assert summary.iloc[0]["広告費"] == 1500
    assert summary.iloc[0]["CV"] == 2


def test_build_person_yahoo_adgroup(builder, asp_df, yahoo_df):
    assignment = {
        "cases": [],
        "platforms": [{"platform": "Yahoo", "unit": "広告グループID", "id": "888"}],
    }
    detail, summary = builder.build_person("井上さん", assignment, asp_df, yahoo_df)
    assert len(detail) == 1
    assert summary.iloc[0]["広告費"] == 1200


@pytest.fixture
def google_df():
    return pd.DataFrame([
        {"date": "2026-06-08", "account_id": "g1", "account_name": "gacc",
         "campaign_id": "555", "campaign_name": "GC1", "adgroup_id": "666",
         "adgroup_name": "GG1", "impressions": 200, "clicks": 10, "cost": 2000,
         "conversions": 4},
    ])


def test_build_person_google_campaign(builder, asp_df, yahoo_df, google_df):
    assignment = {
        "cases": [],
        "platforms": [{"platform": "Google", "unit": "キャンペーンID", "id": "555"}],
    }
    detail, summary = builder.build_person("井上さん", assignment, asp_df, yahoo_df, google_df)
    assert len(detail) == 1
    assert detail.iloc[0]["種別"] == "google"
    assert summary.iloc[0]["広告費"] == 2000
    assert summary.iloc[0]["CV"] == 4


def test_build_person_unknown_platform_skipped(builder, asp_df, yahoo_df):
    assignment = {
        "cases": [],
        "platforms": [{"platform": "TikTok", "unit": "広告グループID", "id": "999"}],
    }
    detail, summary = builder.build_person("井上さん", assignment, asp_df, yahoo_df)
    assert len(detail) == 0
    assert len(summary) == 0  # 未対応媒体は集計にも出さない


def test_build_person_empty_assignment(builder, asp_df, yahoo_df):
    detail, summary = builder.build_person(
        "新人さん", {"cases": [], "platforms": []}, asp_df, yahoo_df
    )
    assert len(detail) == 0
    assert len(summary) == 0
    assert list(detail.columns) == DETAIL_COLUMNS
    assert list(summary.columns) == SUMMARY_COLUMNS


# ── マスタ抽出 ──────────────────────────────────────────────
@pytest.fixture
def asp_df_full():
    return pd.DataFrame([
        {"date": "d", "asp_name": "Felmat", "case_name": "案件A",
         "site_id": "S001", "reward": 1000, "promo_id": "P1", "site_name": "サイトX"},
        {"date": "d", "asp_name": "Felmat", "case_name": "案件A",
         "site_id": "S002", "reward": 1500, "promo_id": "P1", "site_name": "サイトY"},
        {"date": "d", "asp_name": "レントラックス", "case_name": "案件C",
         "site_id": "R01", "reward": 700, "promo_id": "", "site_name": "サイトZ"},
        {"date": "d", "asp_name": "A8.net", "case_name": "案件B",
         "site_id": "", "reward": 500, "promo_id": "PG9", "site_name": ""},
        {"date": "d", "asp_name": "afb", "case_name": "案件D",
         "site_id": "F01", "reward": 300, "promo_id": "", "site_name": "サイトW"},
    ])


def test_extract_case_master(builder, asp_df_full):
    master = builder.extract_case_master(asp_df_full)
    assert master == [
        {"asp_name": "A8.net", "case_name": "案件B", "promo_id": "PG9"},
        {"asp_name": "Felmat", "case_name": "案件A", "promo_id": "P1"},
        {"asp_name": "afb", "case_name": "案件D", "promo_id": ""},
        {"asp_name": "レントラックス", "case_name": "案件C", "promo_id": ""},
    ]


def test_extract_case_master_empty(builder):
    assert builder.extract_case_master(pd.DataFrame()) == []


def test_extract_site_master_only_target_asps(builder, asp_df_full):
    sites = builder.extract_site_master(asp_df_full)
    # Felmat 2サイト + レントラックス 1サイト + afb 1サイト（A8.netは対象外）
    assert len(sites) == 4
    assert all(s["asp_name"] in ("Felmat", "レントラックス", "afb") for s in sites)
    assert {"asp_name": "afb", "case_name": "案件D",
            "site_name": "サイトW", "site_id": "F01"} in sites
    assert {"asp_name": "Felmat", "case_name": "案件A",
            "site_name": "サイトX", "site_id": "S001"} in sites


def test_extract_ad_master(builder, yahoo_df):
    ads = builder.extract_ad_master(yahoo_df)
    camps = [a for a in ads if a["unit"] == "キャンペーン"]
    adgs = [a for a in ads if a["unit"] == "広告グループ"]
    assert camps == [{"platform": "Yahoo", "unit": "キャンペーン",
                      "name": "C1", "id": "777"}]
    assert len(adgs) == 2  # G1/888, G2/889


def test_extract_ad_master_empty(builder):
    assert builder.extract_ad_master(pd.DataFrame()) == []
