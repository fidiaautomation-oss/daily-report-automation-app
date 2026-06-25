import pandas as pd

from phase2.build_personal_split import PersonalSplitter


def _yahoo_csv():
    return (
        "date,account_id,account_name,campaign_id,campaign_name,"
        "adgroup_id,adgroup_name,impressions,clicks,cost,conversions\n"
        "2026-06-22,1,acc,777,C1,888,G1,100,5,1200,2\n"
        "2026-06-22,1,acc,999,C2,111,G2,50,1,300,0\n"
    ).encode("utf-8-sig")


def _felmat_csv():
    # 原本の全列を保持できることを確認（余分な列も残る）
    return (
        "成果番号,Click日時,発生日時,確定日時,プロモーションID,プロモーション,"
        "成果報酬（税抜）,サイトID,サイト,余分列\n"
        "1,x,2026-06-22,,P1,案件A,1000,S001,サイトX,foo\n"
        "2,x,2026-06-22,,P2,案件B,500,S002,サイトY,bar\n"
    ).encode("shift_jis")


def test_filter_ad_by_campaign():
    s = PersonalSplitter()
    raw = {"yahoo_ads.csv": _yahoo_csv()}
    pf = [{"platform": "Yahoo", "unit": "キャンペーンID", "id": "777"}]
    df = s.filter_ad(raw, "Yahoo", pf)
    assert len(df) == 1
    assert df.iloc[0]["campaign_id"] == "777"
    # 原本列を保持
    assert "account_name" in df.columns


def test_filter_asp_keeps_original_columns():
    s = PersonalSplitter()
    raw = {"felmat_f.csv": _felmat_csv()}
    cases = [{"asp_name": "Felmat", "case_name": "案件A", "site_id": ""}]
    df = s.filter_asp(raw, "Felmat", cases)
    assert len(df) == 1
    assert df.iloc[0]["プロモーション"] == "案件A"
    # 原本の全列（余分列含む）が残る
    assert "余分列" in df.columns
    assert df.iloc[0]["余分列"] == "foo"


def test_filter_asp_site_id_filter():
    s = PersonalSplitter()
    raw = {"felmat_f.csv": _felmat_csv()}
    cases = [{"asp_name": "Felmat", "case_name": "案件A", "site_id": "S999"}]
    df = s.filter_asp(raw, "Felmat", cases)
    assert len(df) == 0  # サイトID不一致


def test_build_for_person_splits_sources():
    s = PersonalSplitter()
    raw = {"yahoo_ads.csv": _yahoo_csv(), "felmat_f.csv": _felmat_csv()}
    assignment = {
        "cases": [{"asp_name": "Felmat", "case_name": "案件A", "site_id": ""}],
        "platforms": [{"platform": "Yahoo", "unit": "キャンペーンID", "id": "777"}],
    }
    out = s.build_for_person(raw, assignment)
    assert set(out.keys()) == {"Yahoo", "Felmat"}
    assert len(out["Yahoo"]) == 1
    assert len(out["Felmat"]) == 1


def test_build_for_person_empty():
    s = PersonalSplitter()
    raw = {"yahoo_ads.csv": _yahoo_csv()}
    assignment = {"cases": [], "platforms": []}
    assert s.build_for_person(raw, assignment) == {}
