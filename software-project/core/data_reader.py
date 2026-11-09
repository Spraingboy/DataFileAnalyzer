"""受限读取与导入校验，不写磁盘或数据库。"""

import csv
import threading
from dataclasses import dataclass
from io import BytesIO, StringIO

import pandas as pd
from openpyxl import load_workbook

import config

_CSV_LOCK = threading.Lock()


class DataReadError(ValueError):
    """可向用户展示的格式或数据限制错误。"""


@dataclass
class ReadResult:
    frame: pd.DataFrame
    encoding: str | None


def _check_limits(rows: int, columns: int) -> None:
    if columns > config.MAX_DATA_COLUMNS:
        raise DataReadError(f"数据列数超过 {config.MAX_DATA_COLUMNS} 列限制。")
    if rows > config.MAX_DATA_ROWS:
        raise DataReadError(f"数据行数超过 {config.MAX_DATA_ROWS} 行限制（不含表头）。")


def _check_shape(rows: int, columns: int) -> None:
    _check_limits(rows, columns)
    if rows == 0 or columns == 0:
        raise DataReadError("文件没有可导入的数据，请提供表头和至少一行数据。")


def _read_text(content: bytes, file_type: str) -> ReadResult:
    encodings = config.SUPPORTED_ENCODINGS
    if content.startswith(b"\xef\xbb\xbf"):
        encodings = ("utf-8-sig", "utf-8", "gb18030")
    text = None
    used_encoding = None
    for encoding in encodings:
        try:
            text = content.decode(encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise DataReadError("无法解码文件，请使用 UTF-8、UTF-8-SIG 或 GB18030 编码。")
    if any(ord(char) < 32 and char not in "\t\r\n" for char in text):
        raise DataReadError("文件含有二进制控制字符，请检查文件内容与编码。")
    # csv 字段长度上限为进程级配置，提高后必须恢复，并保护并发读取。
    with _CSV_LOCK:
        old_limit = csv.field_size_limit()
        try:
            csv.field_size_limit(config.MAX_FILE_SIZE_BYTES)
            reader = csv.reader(
                StringIO(text, newline=""),
                delimiter="\t" if file_type == "tsv" else ",", strict=True,
            )
            header = next((row for row in reader if row), [])
            if not header or not any(value.strip() for value in header):
                raise DataReadError("文件为空或没有有效表头。")
            if len(header) > config.MAX_DATA_COLUMNS:
                raise DataReadError(f"数据列数超过 {config.MAX_DATA_COLUMNS} 列限制。")
            rows = []
            for row in reader:
                if not row:  # 真正空白行忽略；用分隔符表示的空值行仍计数。
                    continue
                if len(row) != len(header):
                    raise DataReadError(f"第 {reader.line_num} 个文本行附近字段数量与表头不一致。")
                rows.append(row)
                if len(rows) > config.MAX_DATA_ROWS:
                    raise DataReadError(f"数据行数超过 {config.MAX_DATA_ROWS} 行限制（不含表头）。")
        except csv.Error as exc:
            raise DataReadError("CSV/TSV 格式损坏，请检查引号和分隔符。") from exc
        finally:
            csv.field_size_limit(old_limit)
    _check_shape(len(rows), len(header))
    return ReadResult(pd.DataFrame(rows, columns=header), used_encoding)


def _read_excel(content: bytes) -> ReadResult:
    try:
        with BytesIO(content) as stream:
            workbook = load_workbook(stream, read_only=True, data_only=True)
            try:
                if not workbook.worksheets:
                    raise DataReadError("Excel 文件没有工作表。")
                sheet = workbook.worksheets[config.EXCEL_SHEET_INDEX]
                # 读取前检查工作表范围，避免异常尺寸导致无界展开。
                declared_columns = sheet.max_column or 0
                _check_limits(max((sheet.max_row or 0) - 1, 0), declared_columns)
                # 不完全信任 XLSX 中的 dimension 声明；检查实际 XML 行内容。
                # 保留实际列范围，避免漏掉第 101 列为空、后续列有值的稀疏行。
                # 每读取一行立即检查行列上限，不展开整个工作表。
                sheet.reset_dimensions()
                values = sheet.iter_rows(values_only=True)

                def trim(row):
                    row = list(row)
                    while row and row[-1] is None:
                        row.pop()
                    return row

                raw_header = next(values, ())
                _check_limits(0, len(raw_header))
                header = trim(raw_header)
                width = max(declared_columns, len(header))
                _check_limits(0, width)
                if not any(value is not None and str(value).strip() for value in header):
                    raise DataReadError("Excel 第一个工作表没有有效表头。")
                rows = []
                for row in values:
                    _check_limits(len(rows) + 1, len(row))
                    row = trim(row)
                    width = max(width, len(row))
                    _check_limits(len(rows) + 1, width)
                    rows.append(row)
                _check_shape(len(rows), width)
                # 空白单元格补齐，保证不同有效长度的 Excel 行保留原列位置。
                header.extend([None] * (width - len(header)))
                padded = [row + [None] * (width - len(row)) for row in rows]
                return ReadResult(pd.DataFrame(padded, columns=header), None)
            finally:
                workbook.close()
    except DataReadError:
        raise
    except Exception as exc:
        raise DataReadError("无法读取 XLSX 文件，文件可能损坏、加密或并非有效的 Excel 文件。") from exc


def read_data(content: bytes, file_type: str) -> ReadResult:
    """首行为表头；文本按逻辑记录计行，Excel 按首表使用范围计行。"""
    if file_type not in config.SUPPORTED_EXTENSIONS:
        raise DataReadError("仅支持 CSV、TSV、XLSX 文件。")
    if not content:
        raise DataReadError("文件为空，无法导入。")
    if len(content) > config.MAX_FILE_SIZE_BYTES:
        raise DataReadError(f"单文件大小不能超过 {config.MAX_FILE_SIZE_MB}MB。")
    return _read_excel(content) if file_type == "xlsx" else _read_text(content, file_type)
