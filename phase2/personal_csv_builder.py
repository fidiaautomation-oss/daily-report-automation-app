"""Phase2: 個人別CSV生成。

Drive raw/YYYY-MM-DD/ のCSVと案件管理シートを突合し、運用者ごとに
担当案件のデータのみを集めた明細CSV・集計CSVを生成して
Drive personal/YYYY-MM-DD/ へ保存する。

実行:
    python -m phase2.personal_csv_builder            # 昨日分
    python -m phase2.personal_csv_builder 2026-06-08 # 日付指定
"""

import io
import os
import sys
import logging
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

import pandas as pd
import yaml
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DETAIL_COLUMNS = [
    "date", "種別", "ASP名・媒体", "案件名", "サイトID", "報酬額",
    "campaign_id", "campaign_name", "adgroup_id", "adgroup_name",
    "impressions", "clicks", "cost", "conversions",
]
SUMMARY_COLUMNS = [
    "種別", "ASP名・媒体", "案件名・ID", "発生件数", "報酬合計",
    "広告費", "クリック", "インプレッション", "CV",
]


class PersonalCsvBuilder:
    def __init__(self, mapping_path: str = "config/normalize_mapping.yaml"):
        with open(mapping_path, encoding="utf-8") as f:
            self.asp_normalize = yaml.safe_load(f)["asp_normalize"]

    # ── 正規化 ──────────────────────────────────────────────
    def normalize_asp(self, raw_files: dict) -> pd.DataFrame:
        """{ファイル名: bytes} からASP成果明細の統一DataFrameを作る。

        統一列: date / asp_name / case_name / site_id / reward
        """
        frames = []
        for asp_name, conf in self.asp_normalize.items():
            for fname in conf["files"]:
                if fname not in raw_files:
                    logger.warning(f"raw CSVなし・スキップ: {fname} ({asp_name})")
                    continue
                data = raw_files[fname]
                if not data:
                    logger.info(f"空ファイル・スキップ: {fname}")
                    continue
                try:
                    df = pd.read_csv(
                        io.BytesIO(data), encoding=conf["encoding"], dtype=str
                    )
                except Exception as e:
                    logger.warning(f"読込失敗・スキップ: {fname}: {e}")
                    continue
                if conf["case_col"] not in df.columns:
                    logger.warning(
                        f"案件名列 '{conf['case_col']}' が {fname} にありません・スキップ"
                    )
                    continue
                out = pd.DataFrame()
                out["date"] = df.get(conf["date_col"], "")
                out["asp_name"] = asp_name
                out["case_name"] = df[conf["case_col"]].astype(str).str.strip()
                site_col = conf.get("site_col")
                out["site_id"] = (
                    df[site_col].astype(str).str.strip()
                    if site_col and site_col in df.columns else ""
                )
                promo_col = conf.get("promo_id_col")
                out["promo_id"] = (
                    df[promo_col].astype(str).str.strip()
                    if promo_col and promo_col in df.columns else ""
                )
                site_name_col = conf.get("site_name_col")
                out["site_name"] = (
                    df[site_name_col].astype(str).str.strip()
                    if site_name_col and site_name_col in df.columns else ""
                )
                reward_col = conf.get("reward_col")
                if reward_col and reward_col in df.columns:
                    out["reward"] = (
                        df[reward_col].astype(str)
                        .str.replace(",", "").str.replace("円", "")
                    )
                    out["reward"] = pd.to_numeric(out["reward"], errors="coerce").fillna(0)
                else:
                    out["reward"] = 0
                frames.append(out)
        if not frames:
            return pd.DataFrame(columns=["date", "asp_name", "case_name", "site_id", "reward", "promo_id", "site_name"])
        return pd.concat(frames, ignore_index=True)

    def _normalize_ad_csv(self, raw_files: dict, fname: str) -> pd.DataFrame:
        if fname not in raw_files or not raw_files[fname]:
            logger.warning(f"{fname} がありません")
            return pd.DataFrame()
        df = pd.read_csv(io.BytesIO(raw_files[fname]), encoding="utf-8-sig", dtype=str)
        for col in ["impressions", "clicks", "cost", "conversions"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df

    def normalize_yahoo(self, raw_files: dict) -> pd.DataFrame:
        return self._normalize_ad_csv(raw_files, "yahoo_ads.csv")

    def normalize_google(self, raw_files: dict) -> pd.DataFrame:
        return self._normalize_ad_csv(raw_files, "google_ads.csv")

    # 配信プラットフォーム名（シート入力）→ 媒体キー
    PLATFORM_ALIASES = {
        "yahoo": "Yahoo", "yahoo!": "Yahoo", "yahoo広告": "Yahoo",
        "google": "Google", "google広告": "Google", "googleads": "Google",
    }

    # ── 突合 ────────────────────────────────────────────────
    def build_person(self, person: str, assignment: dict,
                     asp_df: pd.DataFrame, yahoo_df: pd.DataFrame,
                     google_df: pd.DataFrame = None) -> tuple:
        """1運用者分の (明細DF, 集計DF) を返す。"""
        details = []
        summaries = []
        ad_dfs = {
            "Yahoo": yahoo_df if yahoo_df is not None else pd.DataFrame(),
            "Google": google_df if google_df is not None else pd.DataFrame(),
        }

        for case in assignment.get("cases", []):
            m = asp_df[
                (asp_df["asp_name"] == case["asp_name"])
                & (asp_df["case_name"] == case["case_name"])
            ] if len(asp_df) else pd.DataFrame(columns=["date", "asp_name", "case_name", "site_id", "reward"])
            if len(m) and case.get("site_id"):
                m = m[m["site_id"] == case["site_id"]]
            if len(m) == 0:
                logger.info(f"  [{person}] {case['asp_name']}/{case['case_name']}: 0件")
            for _, row in m.iterrows():
                details.append({
                    "date": row["date"], "種別": "asp",
                    "ASP名・媒体": case["asp_name"], "案件名": case["case_name"],
                    "サイトID": row["site_id"], "報酬額": row["reward"],
                })
            summaries.append({
                "種別": "asp", "ASP名・媒体": case["asp_name"],
                "案件名・ID": case["case_name"],
                "発生件数": len(m), "報酬合計": m["reward"].sum() if len(m) else 0,
                "広告費": "", "クリック": "", "インプレッション": "", "CV": "",
            })

        for pf in assignment.get("platforms", []):
            media = self.PLATFORM_ALIASES.get(
                pf["platform"].strip().lower().replace(" ", "")
            )
            if media is None:
                logger.info(f"  [{person}] 媒体 '{pf['platform']}' は未対応・スキップ")
                continue
            ad_df = ad_dfs.get(media, pd.DataFrame())
            if not len(ad_df):
                continue
            key = "campaign_id" if "キャンペーン" in (pf.get("unit") or "") else "adgroup_id"
            m = ad_df[ad_df[key].astype(str).str.strip() == str(pf["id"]).strip()]
            media_key = media.lower()
            for _, row in m.iterrows():
                details.append({
                    "date": row["date"], "種別": media_key,
                    "ASP名・媒体": media, "案件名": row.get("campaign_name", ""),
                    "campaign_id": row.get("campaign_id", ""),
                    "campaign_name": row.get("campaign_name", ""),
                    "adgroup_id": row.get("adgroup_id", ""),
                    "adgroup_name": row.get("adgroup_name", ""),
                    "impressions": row.get("impressions", 0),
                    "clicks": row.get("clicks", 0),
                    "cost": row.get("cost", 0),
                    "conversions": row.get("conversions", 0),
                })
            summaries.append({
                "種別": media_key, "ASP名・媒体": media,
                "案件名・ID": f"{pf.get('unit', '')}:{pf['id']}",
                "発生件数": "", "報酬合計": "",
                "広告費": m["cost"].sum() if len(m) else 0,
                "クリック": m["clicks"].sum() if len(m) else 0,
                "インプレッション": m["impressions"].sum() if len(m) else 0,
                "CV": m["conversions"].sum() if len(m) else 0,
            })

        detail_df = pd.DataFrame(details, columns=DETAIL_COLUMNS)
        summary_df = pd.DataFrame(summaries, columns=SUMMARY_COLUMNS)
        return detail_df, summary_df

    # ── マスタ抽出 ──────────────────────────────────────────
    # サイトマスタの対象ASP（サイト名プルダウンを提供するASP）
    SITE_MASTER_ASPS = ["Felmat", "レントラックス", "afb"]

    @staticmethod
    def extract_case_master(asp_df: pd.DataFrame) -> list:
        """案件名マスタ: (ASP名, 案件名, プロモーションID) の一意リスト。"""
        if not len(asp_df):
            return []
        cols = ["asp_name", "case_name"]
        df = asp_df.copy()
        if "promo_id" not in df.columns:
            df["promo_id"] = ""
        # 同一案件で複数IDが混在する場合は最初の非空IDを採用
        pairs = (
            df.sort_values("promo_id", ascending=False)
            .drop_duplicates(subset=cols)
            .sort_values(cols)
        )
        return [
            {"asp_name": r["asp_name"], "case_name": r["case_name"],
             "promo_id": r.get("promo_id", "")}
            for _, r in pairs.iterrows()
        ]

    @classmethod
    def extract_site_master(cls, asp_df: pd.DataFrame) -> list:
        """サイトマスタ: Felmat/レントラックスの (ASP名, 案件名, サイト名, サイトID)。"""
        if not len(asp_df) or "site_name" not in asp_df.columns:
            return []
        df = asp_df[
            asp_df["asp_name"].isin(cls.SITE_MASTER_ASPS)
            & (asp_df["site_name"].astype(str).str.strip() != "")
        ]
        if not len(df):
            return []
        pairs = (
            df[["asp_name", "case_name", "site_name", "site_id"]]
            .drop_duplicates()
            .sort_values(["asp_name", "case_name", "site_name"])
        )
        return [dict(r) for _, r in pairs.iterrows()]

    @staticmethod
    def extract_ad_master(yahoo_df: pd.DataFrame, google_df: pd.DataFrame = None) -> list:
        """広告マスタ: (配信プラットフォーム, 取得単位, 名称, ID) の一意リスト。"""
        out = []
        for platform, df in [("Yahoo", yahoo_df), ("Google", google_df)]:
            if df is None or not len(df):
                continue
            if "campaign_id" in df.columns:
                camp = df[["campaign_name", "campaign_id"]].dropna().drop_duplicates()
                for _, r in camp.sort_values("campaign_name").iterrows():
                    out.append({"platform": platform, "unit": "キャンペーン",
                                "name": r["campaign_name"], "id": r["campaign_id"]})
            if "adgroup_id" in df.columns:
                adg = df[["adgroup_name", "adgroup_id"]].dropna().drop_duplicates()
                for _, r in adg.sort_values("adgroup_name").iterrows():
                    out.append({"platform": platform, "unit": "広告グループ",
                                "name": r["adgroup_name"], "id": r["adgroup_id"]})
        return out


def main():
    from phase1.drive_uploader import DriveUploader
    from phase2.sheet_reader import SheetReader
    import tempfile

    date_str = sys.argv[1] if len(sys.argv) > 1 else (
        datetime.now(JST) - timedelta(days=1)
    ).date().isoformat()
    logger.info(f"対象日付: {date_str}")

    uploader = DriveUploader()
    builder = PersonalCsvBuilder()
    reader = SheetReader()

    raw_files = uploader.download_folder_csvs(date_str, top_folder="raw")
    logger.info(f"raw CSV取得: {len(raw_files)}ファイル")

    asp_df = builder.normalize_asp(raw_files)
    yahoo_df = builder.normalize_yahoo(raw_files)
    google_df = builder.normalize_google(raw_files)
    logger.info(
        f"ASP明細: {len(asp_df)}行 / Yahoo: {len(yahoo_df)}行 / Google: {len(google_df)}行"
    )

    # マスタ3タブ（案件名・サイト・広告）を前日CSVデータで自動更新し、
    # 入力支援（連動プルダウン・自動反映数式）を再設定する
    reader.update_masters(
        builder.extract_case_master(asp_df),
        builder.extract_site_master(asp_df),
        builder.extract_ad_master(yahoo_df, google_df),
    )
    reader.setup_input_helpers()

    assignments = reader.read_assignments()
    logger.info(f"運用者: {list(assignments.keys())}")

    for person, assignment in assignments.items():
        detail_df, summary_df = builder.build_person(
            person, assignment, asp_df, yahoo_df, google_df
        )
        logger.info(f"[{person}] 明細{len(detail_df)}行 / 集計{len(summary_df)}行")
        for suffix, df in [("明細", detail_df), ("集計", summary_df)]:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
                tmp = f.name
            df.to_csv(tmp, index=False, encoding="utf-8-sig")
            fid = uploader.upload_csv(
                tmp, f"{person}_{suffix}.csv", date_str, top_folder="personal"
            )
            logger.info(f"  アップロード: personal/{date_str}/{person}_{suffix}.csv ({fid})")
            os.unlink(tmp)


if __name__ == "__main__":
    main()
