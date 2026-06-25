"""担当者ごとに、プラットフォーム/ASPごとの「原本形式」CSVを生成してDriveへ保存する。

各ソース（Yahoo / Google / 各ASP）の元の列構成をそのまま保持し、
担当者の担当行だけにフィルタする。ASP原本はcp932のためPythonで処理する。

出力: personal/<日付>/<担当者>_<ソース>.csv（UTF-8 BOM）
  例) personal/2026-06-22/井上さん_Yahoo.csv
      personal/2026-06-22/井上さん_Felmat.csv

実行:
    python -m phase2.build_personal_split            # シートの取得日範囲 or 前日
    python -m phase2.build_personal_split 3
    python -m phase2.build_personal_split 2026-06-15 2026-06-18
"""

import io
import os
import re
import sys
import logging
import tempfile

import pandas as pd
import yaml
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 配信プラットフォーム名 → 広告費rawファイル
AD_FILES = {"Yahoo": "yahoo_ads.csv", "Google": "google_ads.csv"}
SAFE = re.compile(r"[^\wぁ-んァ-ヶ一-龠ー（）()]+")


def _safe(name: str) -> str:
    return SAFE.sub("_", str(name)).strip("_")


class PersonalSplitter:
    def __init__(self, mapping_path: str = "config/normalize_mapping.yaml"):
        with open(mapping_path, encoding="utf-8") as f:
            self.asp_map = yaml.safe_load(f)["asp_normalize"]

    # ── 広告費（原本形式・UTF-8） ──────────────────────────
    def filter_ad(self, raw_files: dict, platform: str, platforms_cfg: list) -> pd.DataFrame:
        """1プラットフォーム分の広告費を、担当者の配信PF設定でフィルタ（原本列のまま）。"""
        fname = AD_FILES.get(platform)
        if not fname or fname not in raw_files or not raw_files[fname]:
            return pd.DataFrame()
        df = pd.read_csv(io.BytesIO(raw_files[fname]), encoding="utf-8-sig", dtype=str)
        wanted_campaign = set()
        wanted_adgroup = set()
        for pf in platforms_cfg:
            if pf["platform"] != platform:
                continue
            if "キャンペーン" in (pf.get("unit") or ""):
                wanted_campaign.add(str(pf["id"]).strip())
            else:
                wanted_adgroup.add(str(pf["id"]).strip())
        mask = pd.Series(False, index=df.index)
        if wanted_campaign and "campaign_id" in df.columns:
            mask |= df["campaign_id"].astype(str).str.strip().isin(wanted_campaign)
        if wanted_adgroup and "adgroup_id" in df.columns:
            mask |= df["adgroup_id"].astype(str).str.strip().isin(wanted_adgroup)
        return df[mask].copy()

    # ── ASP（原本形式・cp932→そのままの列） ────────────────
    def filter_asp(self, raw_files: dict, asp_name: str, cases_cfg: list) -> pd.DataFrame:
        """1ASP分を、担当者の案件設定でフィルタ（原本の全列を保持）。"""
        conf = self.asp_map.get(asp_name)
        if not conf:
            return pd.DataFrame()
        case_col = conf["case_col"]
        site_col = conf.get("site_col")
        # この担当者がこのASPで担当する (案件名, サイトID) の集合
        wanted = [(c["case_name"], c.get("site_id", "")) for c in cases_cfg
                  if c["asp_name"] == asp_name]
        if not wanted:
            return pd.DataFrame()

        frames = []
        for fname in conf["files"]:
            data = raw_files.get(fname)
            if not data:
                continue
            try:
                df = pd.read_csv(io.BytesIO(data), encoding=conf["encoding"], dtype=str)
            except Exception as e:
                logger.warning(f"{fname} 読込失敗・スキップ: {e}")
                continue
            if case_col not in df.columns:
                continue
            mask = pd.Series(False, index=df.index)
            for case_name, site_id in wanted:
                m = df[case_col].astype(str).str.strip() == str(case_name).strip()
                if site_id and site_col and site_col in df.columns:
                    m &= df[site_col].astype(str).str.strip() == str(site_id).strip()
                mask |= m
            if mask.any():
                frames.append(df[mask].copy())
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def build_for_person(self, raw_files: dict, assignment: dict) -> dict:
        """担当者1人分。{ソース名: DataFrame(原本列)} を返す（空は含めない）。"""
        out = {}
        for platform in AD_FILES:
            df = self.filter_ad(raw_files, platform, assignment.get("platforms", []))
            if len(df):
                out[platform] = df
        asp_names = {c["asp_name"] for c in assignment.get("cases", [])}
        for asp_name in sorted(asp_names):
            df = self.filter_asp(raw_files, asp_name, assignment.get("cases", []))
            if len(df):
                out[asp_name] = df
        return out


def _upload_sources(uploader, person, date_str, sources) -> list:
    """{ソース: DataFrame} を personal/<日付>/ へ保存。生成ファイル名のリストを返す。"""
    made = []
    for source, df in sources.items():
        fname = f"{_safe(person)}_{_safe(source)}.csv"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp = f.name
        df.to_csv(tmp, index=False, encoding="utf-8-sig")
        uploader.upload_csv(tmp, fname, date_str, top_folder="personal")
        os.unlink(tmp)
        made.append(fname)
        logger.info(f"  [{date_str}] {person}/{source}: {len(df)}行 → personal/{date_str}/{fname}")
    return made


def generate_for_person(uploader, splitter, person, assignment, start, end) -> list:
    """1担当者分を期間ぶん生成する。生成した (日付, ファイル名) のリストを返す。"""
    from phase1.date_range import date_list

    made = []
    for d in date_list(start, end):
        date_str = d.isoformat()
        raw_files = uploader.download_folder_csvs(date_str, top_folder="raw")
        if not raw_files:
            logger.warning(f"raw/{date_str}/ にデータがありません・スキップ")
            continue
        sources = splitter.build_for_person(raw_files, assignment)
        if not sources:
            logger.info(f"  [{date_str}] {person}: 該当データなし")
            continue
        for fname in _upload_sources(uploader, person, date_str, sources):
            made.append((date_str, fname))
    return made


def main():
    from phase1.drive_uploader import DriveUploader
    from phase1.date_range import resolve_range
    from phase2.sheet_reader import SheetReader

    start, end = resolve_range(sys.argv[1:])
    logger.info(f"担当者別CSV生成 期間: {start}〜{end}")

    uploader = DriveUploader()
    splitter = PersonalSplitter()
    assignments = SheetReader().read_assignments()
    logger.info(f"対象運用者: {list(assignments.keys())}")

    for person, assignment in assignments.items():
        generate_for_person(uploader, splitter, person, assignment, start, end)


if __name__ == "__main__":
    main()
