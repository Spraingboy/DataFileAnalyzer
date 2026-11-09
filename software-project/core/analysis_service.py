"""纯 DataFrame 预览与统计函数，不依赖 Streamlit、磁盘或数据库。"""

import math
import statistics
from typing import Any, Sequence

import pandas as pd
from pandas.api.types import (
    is_bool_dtype, is_complex_dtype, is_datetime64_any_dtype, is_numeric_dtype,
    is_timedelta64_dtype,
    is_scalar,
)


class AnalysisError(ValueError):
    """输入或字段类型不适合当前分析操作。"""


def _is_numeric(series: pd.Series) -> bool:
    return (
        is_numeric_dtype(series.dtype)
        and not is_bool_dtype(series.dtype)
        and not is_complex_dtype(series.dtype)
    )


def prepare_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """复制输入，规范空值、唯一字段名，并保守推断整列数值文本。

    空字符串/纯空白视为缺失；混合文本保留，不把转换失败的值丢弃。
    不把日期、布尔、分类类型强制转换为数值。
    """
    if not isinstance(frame, pd.DataFrame):
        raise AnalysisError("分析输入必须是 Pandas DataFrame。")
    result = frame.copy(deep=True)
    names = []
    used = set()
    for index, label in enumerate(result.columns):
        base = str(label) if label is not None and str(label).strip() else f"未命名字段_{index + 1}"
        name = base
        suffix = 2
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1
        used.add(name)
        names.append(name)
    result.columns = names

    def normalize(value):
        if not is_scalar(value):
            raise AnalysisError("字段包含列表、字典等嵌套数据，无法进行表格统计。")
        if isinstance(value, str):
            return pd.NA if not value.strip() else value
        # 统一 object 列里的 None/NaN/pd.NA，避免单列判重区分缺失标记。
        return pd.NA if pd.isna(value) else value

    for name in names:
        series = result[name]
        if isinstance(series.dtype, pd.CategoricalDtype):
            # 分类空白仍按缺失处理，保留分类语义，不转成数值。
            blank_categories = [v for v in series.cat.categories if isinstance(v, str) and not v.strip()]
            if blank_categories:
                result[name] = series.mask(series.isin(blank_categories))
            continue
        if (
            is_bool_dtype(series.dtype) or is_datetime64_any_dtype(series.dtype)
            or is_timedelta64_dtype(series.dtype) or is_complex_dtype(series.dtype)
        ):
            continue
        if not _is_numeric(series):
            series = series.map(normalize)
            present = series.dropna()
            if not present.empty and not any(isinstance(value, bool) for value in present):
                try:
                    numbers = pd.to_numeric(series, errors="coerce")
                    if numbers.notna().sum() == len(present):
                        series = numbers
                except (TypeError, ValueError, OverflowError):
                    pass
            result[name] = series
    return result


def _fields(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([
        {"field": name, "dtype": str(frame[name].dtype), "numeric": _is_numeric(frame[name])}
        for name in frame.columns
    ], columns=["field", "dtype", "numeric"])


def field_info(frame: pd.DataFrame) -> pd.DataFrame:
    return _fields(prepare_dataframe(frame))


def preview_dataframe(
    frame: pd.DataFrame, columns: Sequence[str] | None = None, limit: int = 20,
) -> pd.DataFrame:
    if limit not in (20, 50, 100):
        raise AnalysisError("预览行数只能选择 20、50 或 100。")
    data = prepare_dataframe(frame)
    selected = list(data.columns) if columns is None else list(columns)
    if len(set(selected)) != len(selected) or any(name not in data.columns for name in selected):
        raise AnalysisError("选择的字段不存在或重复，请重新选择。")
    return data.loc[:, selected].head(limit).copy()


def _duplicate_count(frame: pd.DataFrame) -> int:
    return int(frame.duplicated(keep="first").sum()) if len(frame.columns) else 0


def duplicate_row_count(frame: pd.DataFrame) -> int:
    """相同整行中，首次出现以外的额外记录数。"""
    return _duplicate_count(prepare_dataframe(frame))


def _missing(frame: pd.DataFrame) -> pd.DataFrame:
    rows = len(frame)
    return pd.DataFrame([
        {"field": name, "missing_count": int(frame[name].isna().sum()),
         "missing_rate": float(frame[name].isna().mean()) if rows else None}
        for name in frame.columns
    ], columns=["field", "missing_count", "missing_rate"])


def missing_statistics(frame: pd.DataFrame) -> pd.DataFrame:
    """缺失率返回 0~1 比例；没有数据行时为未定义值。"""
    return _missing(prepare_dataframe(frame))


def _overview(frame: pd.DataFrame) -> dict[str, Any]:
    rows, columns = frame.shape
    missing = int(frame.isna().sum().sum())
    return {
        "row_count": rows, "column_count": columns,
        "numeric_column_count": sum(_is_numeric(frame[name]) for name in frame.columns),
        "missing_count": missing,
        "missing_rate": missing / (rows * columns) if rows and columns else None,
        "duplicate_row_count": _duplicate_count(frame),
    }


def dataset_overview(frame: pd.DataFrame) -> dict[str, Any]:
    return _overview(prepare_dataframe(frame))


def _numeric(frame: pd.DataFrame, columns=None) -> pd.DataFrame:
    selected = [name for name in frame.columns if _is_numeric(frame[name])] if columns is None else list(columns)
    records = []
    for name in selected:
        if name not in frame.columns or not _is_numeric(frame[name]):
            raise AnalysisError(f"字段“{name}”不存在或不是可统计的数值字段。")
        # 无限大参与聚合会生成无效均值/标准差，数值有效数量只计算有限值。
        valid = frame[name].dropna()
        valid = valid[~valid.isin([float("inf"), float("-inf")])]
        record = {"field": name, "count": len(valid)}
        values = valid.tolist()
        ordered = sorted(values)
        middle = len(ordered) // 2
        metrics = {
            # statistics 使用精确比率累加，避免有限大数求和/平方的中间溢出。
            "mean": lambda: statistics.mean(values),
            "median": lambda: ordered[middle] if len(ordered) % 2 else statistics.mean(ordered[middle - 1:middle + 1]),
            "max": valid.max, "min": valid.min,
            "std": lambda: statistics.stdev(values),
        }
        for metric, calculate in metrics.items():
            try:
                value = calculate() if len(valid) and (metric != "std" or len(valid) > 1) else None
            except (OverflowError, statistics.StatisticsError):
                value = None
            record[metric] = float(value) if value is not None and pd.notna(value) and math.isfinite(float(value)) else None
        records.append(record)
    return pd.DataFrame(records, columns=["field", "count", "mean", "median", "max", "min", "std"])


def numeric_statistics(frame: pd.DataFrame, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """按列返回有限值数量和描述统计；样本标准差 ddof=1，不足两项为空。"""
    return _numeric(prepare_dataframe(frame), columns)


def _frequency(frame: pd.DataFrame, field: str, top_n: int) -> pd.DataFrame:
    if field not in frame.columns or _is_numeric(frame[field]):
        raise AnalysisError("请选择存在的分类字段，数值字段不用于分类频次统计。")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise AnalysisError("频次统计项数必须为正整数。")
    counts = frame[field].dropna().value_counts(sort=True)
    counts = counts[counts > 0].head(top_n)
    return pd.DataFrame({"value": [str(value) for value in counts.index], "count": counts.to_numpy(dtype=int)})


def category_frequencies(frame: pd.DataFrame, field: str, top_n: int = 10) -> pd.DataFrame:
    """排除缺失项，按频次降序返回前 N 项；未出现的分类不占名额。"""
    return _frequency(prepare_dataframe(frame), field, top_n)


def analyze_dataframe(frame: pd.DataFrame) -> dict[str, Any]:
    """一次规范化后生成完整报告，所有内容均来自输入数据。"""
    data = prepare_dataframe(frame)
    return {
        "overview": _overview(data), "fields": _fields(data),
        "numeric": _numeric(data), "missing": _missing(data),
        "categorical": {
            name: _frequency(data, name, 10) for name in data.columns if not _is_numeric(data[name])
        },
    }
