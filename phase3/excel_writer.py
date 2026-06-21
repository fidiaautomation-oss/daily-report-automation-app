import logging
import pandas as pd
import openpyxl
import yaml
from openpyxl.utils import column_index_from_string

logger = logging.getLogger(__name__)


class ExcelWriter:
    def __init__(self, mapping: dict):
        self.sheet_name = mapping["sheet_name"]
        self.data_start_row = mapping["data_start_row"]
        self.col_mappings = mapping["mappings"]

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ExcelWriter":
        with open(yaml_path) as f:
            return cls(yaml.safe_load(f))

    def write(self, template_path: str, df: pd.DataFrame, output_path: str) -> None:
        """テンプレートExcelにDataFrameの値を書き込んで output_path へ保存する"""
        wb = openpyxl.load_workbook(template_path, keep_vba=True)
        ws = wb[self.sheet_name]

        for row_idx, row in enumerate(df.itertuples(index=False), start=self.data_start_row):
            for mapping in self.col_mappings:
                csv_col = mapping["csv_col"]
                excel_col = mapping["excel_col"]
                if csv_col not in df.columns:
                    logger.warning(f"CSV列が見つかりません、スキップ: {csv_col}")
                    continue
                col_num = column_index_from_string(excel_col)
                ws.cell(row=row_idx, column=col_num, value=getattr(row, csv_col, None))

        wb.save(output_path)
        logger.info(f"Excel書き込み完了: {output_path}")
