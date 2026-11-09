"""真实构造 CSV/TSV/XLSX 字节，验证读取和产品边界。"""

from io import BytesIO
import re
from zipfile import ZipFile

import pytest
from openpyxl import Workbook

import config
from core.data_reader import DataReadError, read_data


def make_excel(rows, second_sheet=None):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    if second_sheet is not None:
        other = workbook.create_sheet("不应分析")
        for row in second_sheet:
            other.append(row)
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


@pytest.mark.parametrize("file_type,delimiter", [("csv", ","), ("tsv", "\t")])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030"])
def test_text_encodings(file_type, delimiter, encoding):
    text = f"姓名{delimiter}金额\n张三{delimiter}12\n李四{delimiter}\n"
    result = read_data(text.encode(encoding), file_type)
    assert result.frame.shape == (2, 2)
    assert list(result.frame.columns) == ["姓名", "金额"]
    assert result.frame.iloc[0, 0] == "张三"
    assert result.encoding == encoding


def test_quoted_newline_and_empty_cells():
    result = read_data(b'a,b\n"one\ntwo",\n\n,3\n', "csv")
    assert result.frame.shape == (2, 2)
    assert result.frame.iloc[0, 0] == "one\ntwo"
    assert result.frame.iloc[0, 1] == ""


@pytest.mark.parametrize("content,file_type", [
    (b"", "csv"), (b"\n\n", "tsv"), (b"a,b\n", "csv"),
    (b'a,b\n"broken,2', "csv"), (b"a,b\n1,2,3\n", "csv"),
    (b"a,b\n1\n", "csv"), (b"a\x00b\n1", "csv"),
    (b"a\n\xff", "csv"), (b"a\n1", "exe"), (b"not an xlsx", "xlsx"),
])
def test_invalid_files(content, file_type):
    with pytest.raises(DataReadError):
        read_data(content, file_type)


def test_size_boundary():
    # 单个长字段也应支持，不能被 csv 默认的 128KB 字段限制误拒绝。
    exact = b"a\n" + b"x" * (config.MAX_FILE_SIZE_BYTES - 2)
    assert read_data(exact, "csv").frame.shape == (1, 1)
    with pytest.raises(DataReadError, match="10MB"):
        read_data(exact + b"x", "csv")


def test_text_row_boundary():
    exact = b"a\n" + b"1\n" * config.MAX_DATA_ROWS
    assert read_data(exact, "csv").frame.shape == (50_000, 1)
    with pytest.raises(DataReadError, match="50000"):
        read_data(exact + b"2\n", "csv")


@pytest.mark.parametrize("file_type,separator", [("csv", b","), ("tsv", b"\t")])
def test_text_column_boundary(file_type, separator):
    def content(count):
        return separator.join([b"c"] * count) + b"\n" + separator.join([b"1"] * count)
    assert read_data(content(100), file_type).frame.shape == (1, 100)
    with pytest.raises(DataReadError, match="100"):
        read_data(content(101), file_type)


def test_excel_only_first_sheet():
    content = make_excel([["姓名", "值"], ["甲", 12]], [["x"] * 101, [1] * 101])
    result = read_data(content, "xlsx")
    assert result.frame.shape == (1, 2)
    assert result.frame.iloc[0, 1] == 12
    assert result.encoding is None


@pytest.mark.parametrize("rows", [[], [["a"]]])
def test_empty_excel(rows):
    with pytest.raises(DataReadError):
        read_data(make_excel(rows), "xlsx")


def test_excel_column_boundary():
    assert read_data(make_excel([["c"] * 100, [1] * 100]), "xlsx").frame.shape == (1, 100)
    with pytest.raises(DataReadError, match="100"):
        read_data(make_excel([["c"] * 101, [1] * 101]), "xlsx")


def test_excel_row_boundary():
    exact = [["a"], *[[1] for _ in range(config.MAX_DATA_ROWS)]]
    assert read_data(make_excel(exact), "xlsx").frame.shape == (50_000, 1)
    with pytest.raises(DataReadError, match="50000"):
        read_data(make_excel([*exact, [2]]), "xlsx")


def with_false_dimensions(content):
    output = BytesIO()
    with ZipFile(BytesIO(content)) as source, ZipFile(output, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = re.sub(rb'<dimension ref="[^"]+"', b'<dimension ref="A1:A2"', data)
            target.writestr(item, data)
    return output.getvalue()


def test_excel_misleading_dimensions_cannot_hide_columns():
    content = with_false_dimensions(make_excel([["c"] * 101, [1] * 101]))
    with pytest.raises(DataReadError, match="100"):
        read_data(content, "xlsx")


def test_excel_misleading_dimensions_cannot_hide_rows(monkeypatch):
    # 用小阈值验证底层 XML 读取分支，真实 50000 行边界另有测试。
    monkeypatch.setattr(config, "MAX_DATA_ROWS", 2)
    content = with_false_dimensions(make_excel([["a"], [1], [2], [3]]))
    with pytest.raises(DataReadError, match="行限制"):
        read_data(content, "xlsx")


def test_excel_underreported_dimensions_and_blank_cells():
    content = with_false_dimensions(make_excel([["a", "b"], [None, 2], [3, None]]))
    result = read_data(content, "xlsx")
    assert result.frame.shape == (2, 2)
    assert result.frame.iloc[0, 1] == 2
    assert result.frame.iloc[1, 0] == 3


def test_excel_sparse_out_of_range_column_cannot_be_hidden():
    content = with_false_dimensions(make_excel([["a"], [None] * 101 + [1]]))
    with pytest.raises(DataReadError, match="100"):
        read_data(content, "xlsx")
