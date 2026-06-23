import pandas as pd

from phase2.export_normalized import build_normalized_asp, NORMALIZED_COLUMNS


def test_build_normalized_asp_felmat():
    csv = (
        "成果番号,Click日時,発生日時,確定日時,プロモーションID,プロモーション,"
        "成果報酬（税抜）,サイトID,サイト\n"
        "1,2026-06-08 09:00,2026-06-08 10:00,,P1,案件A,1000,S001,サイトX\n"
    ).encode("shift_jis")
    df = build_normalized_asp({"felmat_f.csv": csv})
    assert list(df.columns) == NORMALIZED_COLUMNS
    assert len(df) == 1
    row = df.iloc[0]
    assert row["asp_name"] == "Felmat"
    assert row["case_name"] == "案件A"
    assert row["promo_id"] == "P1"
    assert row["site_name"] == "サイトX"
    assert row["site_id"] == "S001"
    assert row["reward"] == 1000
    assert row["count"] == 1


def test_build_normalized_asp_empty():
    df = build_normalized_asp({})
    assert len(df) == 0
    assert list(df.columns) == NORMALIZED_COLUMNS
