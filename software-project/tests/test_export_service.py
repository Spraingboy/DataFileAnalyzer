"""重新读回导出文件，核对真实内容、顺序及统计口径。"""

import csv
from io import BytesIO, StringIO

import pandas as pd
import pytest
from openpyxl import load_workbook
from pandas.testing import assert_frame_equal

from core.export_service import (
    ExportError, export_missing_statistics, export_numeric_statistics,
    export_selected_csv, export_selected_xlsx,
)


def test_csv_preserves_selected_order_values_and_row_count():
    frame = pd.DataFrame({"编号": ["001", "002"], "文本": ['甲,乙', '含"引号"\n换行'], "忽略": [9, 8]})
    original = frame.copy(deep=True)
    content = export_selected_csv(frame, ["文本", "编号"])
    assert content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(StringIO(content.decode("utf-8-sig"))))
    assert rows == [["文本", "编号"], ["甲,乙", "001"], ['含"引号"\n换行', "002"]]
    assert_frame_equal(frame, original)


def test_excel_round_trip_preserves_formula_like_text_and_values():
    frame = pd.DataFrame({"编号": ["001", "002"], "=字段": ["=1+2", "普通文本"], "忽略": [9, 8]})
    content = export_selected_xlsx(frame, ["=字段", "编号"])
    with BytesIO(content) as buffer:
        workbook = load_workbook(buffer, data_only=False)
        assert workbook.sheetnames == ["数据"]
        sheet = workbook.active
        assert list(sheet.values) == [("=字段", "编号"), ("=1+2", "001"), ("普通文本", "002")]
        assert sheet["A1"].data_type == "s"
        assert sheet["A2"].data_type == "s"
        workbook.close()


def test_statistics_export_only_selected_fields_and_full_data():
    frame = pd.DataFrame({"amount": [*range(3000), None], "other": range(3001), "label": ["A"] * 3001})
    numeric = pd.read_csv(BytesIO(export_numeric_statistics(frame, ["amount", "label"])))
    assert numeric["字段"].tolist() == ["amount"]
    assert numeric.iloc[0]["有效值数量"] == 3000
    assert numeric.iloc[0]["均值"] == 1499.5
    missing = pd.read_csv(BytesIO(export_missing_statistics(frame, ["label", "amount"])))
    assert missing["字段"].tolist() == ["label", "amount"]
    assert missing.iloc[1]["缺失数量"] == 1
    assert missing.iloc[1]["缺失率"] == pytest.approx(1 / 3001)


@pytest.mark.parametrize("exporter", [export_selected_csv, export_selected_xlsx, export_numeric_statistics, export_missing_statistics])
def test_invalid_selection_and_empty_frames(exporter):
    frame = pd.DataFrame({"x": [1, 2]})
    for columns in ([], ["missing"], ["x", "x"]):
        with pytest.raises(ExportError):
            exporter(frame, columns)
    with pytest.raises(ExportError, match="没有可导出"):
        exporter(pd.DataFrame({"x": []}), ["x"])


def test_all_empty_values_have_meaningful_missing_export():
    frame = pd.DataFrame({"empty": [None, " "]})
    result = pd.read_csv(BytesIO(export_missing_statistics(frame, ["empty"])))
    assert result.iloc[0]["缺失数量"] == 2
    assert result.iloc[0]["缺失率"] == 1
    with pytest.raises(ExportError, match="没有数值统计"):
        export_numeric_statistics(frame, ["empty"])


def test_numeric_csv_uses_known_sample_standard_deviation():
    result = pd.read_csv(BytesIO(export_numeric_statistics(pd.DataFrame({"x": [1, 2, 3]}), ["x"])))
    assert result.iloc[0]["均值"] == 2
    assert result.iloc[0]["标准差"] == 1


def test_excel_rejects_long_strings_without_truncation():
    frame = pd.DataFrame({"text": ["x" * 32768]})
    with pytest.raises(ExportError, match="32767"):
        export_selected_xlsx(frame, ["text"])
    assert "x" * 32768 in export_selected_csv(frame, ["text"]).decode("utf-8-sig")


def test_export_failures_are_wrapped(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("serialization failed")
    frame = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(pd.DataFrame, "to_csv", fail)
    monkeypatch.setattr(pd.DataFrame, "to_excel", fail)
    with pytest.raises(ExportError, match="CSV 导出失败"):
        export_selected_csv(frame, ["x"])
    with pytest.raises(ExportError, match="XLSX 导出失败"):
        export_selected_xlsx(frame, ["x"])
