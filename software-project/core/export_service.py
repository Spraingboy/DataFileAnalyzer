"""纯内存导出，保持选中字段顺序及原始单元格值。"""

from io import BytesIO
from itertools import chain
from typing import Sequence

import pandas as pd

from core.analysis_service import AnalysisError, missing_statistics, numeric_statistics, prepare_dataframe

NUMERIC_LABELS = {"field": "字段", "count": "有效值数量", "mean": "均值", "median": "中位数", "max": "最大值", "min": "最小值", "std": "标准差"}
MISSING_LABELS = {"field": "字段", "missing_count": "缺失数量", "missing_rate": "缺失率"}


class ExportError(ValueError):
    """没有有效导出内容，或序列化失败。"""


def _selected(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    try:
        # 仅借用统一字段名称，不将类型推断写入选列导出的原始值。
        names = prepare_dataframe(frame).columns
    except AnalysisError as exc:
        raise ExportError(str(exc)) from exc
    data = frame.copy(deep=True)
    data.columns = names
    selected = list(columns)
    if not selected:
        raise ExportError("请至少选择一个导出字段。")
    if len(set(selected)) != len(selected) or any(name not in names for name in selected):
        raise ExportError("导出字段不存在或重复，请重新选择。")
    if data.empty:
        raise ExportError("当前文件没有可导出的数据行。")
    return data.loc[:, selected].copy()


def _csv(data: pd.DataFrame) -> bytes:
    try:
        return data.to_csv(index=False).encode("utf-8-sig")
    except Exception as exc:
        raise ExportError("CSV 导出失败，请检查数据格式。") from exc


def export_selected_csv(frame: pd.DataFrame, columns: Sequence[str]) -> bytes:
    return _csv(_selected(frame, columns))


def export_selected_xlsx(frame: pd.DataFrame, columns: Sequence[str]) -> bytes:
    data = _selected(frame, columns)
    # Excel 会静默截断过长文本，明确拒绝以保证内容一致。
    strings = chain(data.columns, (value for row in data.itertuples(index=False, name=None) for value in row if isinstance(value, str)))
    if any(len(value) > 32767 for value in strings):
        raise ExportError("Excel 单元格文本超过 32767 字符，请改用 CSV 导出。")
    try:
        with BytesIO() as buffer:
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                # 预建可见工作表，序列化中途失败时 writer 仍能正常关闭。
                writer.book.create_sheet("数据")
                data.to_excel(writer, sheet_name="数据", index=False)
                # 等号开头的上传文本仍是文本，不能在导出时变成 Excel 公式。
                for row in writer.sheets["数据"].iter_rows():
                    for cell in row:
                        if cell.data_type == "f":
                            cell.data_type = "s"
            return buffer.getvalue()
    except Exception as exc:
        raise ExportError("XLSX 导出失败，请检查单元格类型或改用 CSV。") from exc


def export_numeric_statistics(frame: pd.DataFrame, columns: Sequence[str]) -> bytes:
    result = numeric_statistics(_selected(frame, columns))
    if result.empty:
        raise ExportError("所选字段没有数值统计结果。")
    return _csv(result.rename(columns=NUMERIC_LABELS))


def export_missing_statistics(frame: pd.DataFrame, columns: Sequence[str]) -> bytes:
    result = missing_statistics(_selected(frame, columns))
    return _csv(result.rename(columns=MISSING_LABELS))
