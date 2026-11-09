"""用已知结果核对统计口径，并覆盖异常输入与空数据。"""

import math

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from core.analysis_service import (
    AnalysisError, analyze_dataframe, category_frequencies, dataset_overview,
    duplicate_row_count, field_info, missing_statistics, numeric_statistics,
    prepare_dataframe, preview_dataframe,
)


@pytest.fixture
def known_frame():
    return pd.DataFrame({
        "金额": [1.0, 2.0, 3.0, 4.0, None, 4.0],
        "分类": ["A", "A", "B", "B", None, "B"],
        "全空数值": pd.Series([pd.NA] * 6, dtype="Float64"),
    })


def test_known_numeric_values_and_sample_std(known_frame):
    result = numeric_statistics(known_frame).set_index("field")
    row = result.loc["金额"]
    assert row["count"] == 5
    assert row["mean"] == pytest.approx(2.8)
    assert row["median"] == 3
    assert row["max"] == 4
    assert row["min"] == 1
    # 样本方差 = ((1-2.8)^2+...+(4-2.8)^2)/4 = 1.7。
    assert row["std"] == pytest.approx(math.sqrt(1.7))
    assert result.loc["全空数值", "count"] == 0
    assert result.loc["全空数值", ["mean", "median", "min", "max", "std"]].isna().all()


def test_missing_rates_and_duplicate_count(known_frame):
    missing = missing_statistics(known_frame).set_index("field")
    assert missing.loc["金额", "missing_count"] == 1
    assert missing.loc["金额", "missing_rate"] == pytest.approx(1 / 6)
    assert missing.loc["全空数值", "missing_count"] == 6
    assert missing.loc["全空数值", "missing_rate"] == 1
    assert duplicate_row_count(known_frame) == 1
    assert dataset_overview(known_frame) == {
        "row_count": 6, "column_count": 3, "numeric_column_count": 2,
        "missing_count": 8, "missing_rate": 8 / 18, "duplicate_row_count": 1,
    }


def test_category_top_ten_and_missing_exclusion(known_frame):
    result = category_frequencies(known_frame, "分类")
    assert result.to_dict("records") == [{"value": "B", "count": 3}, {"value": "A", "count": 2}]
    frame = pd.DataFrame({"group": [str(n) for n in range(12) for _ in range(n + 1)]})
    # 用非数字前缀确保这是分类字段。
    frame["group"] = "group_" + frame["group"]
    top = category_frequencies(frame, "group")
    assert len(top) == 10
    assert top.iloc[0].to_dict() == {"value": "group_11", "count": 12}
    assert top.iloc[-1].to_dict() == {"value": "group_2", "count": 3}


def test_numeric_text_blank_normalization_and_no_mutation():
    frame = pd.DataFrame({"value": ["1", "2", "", "  ", None], "mixed": ["1", "bad", "", "x", None]})
    original = frame.copy(deep=True)
    report = analyze_dataframe(frame)
    assert_frame_equal(frame, original)
    assert report["numeric"].iloc[0]["count"] == 2
    assert report["numeric"].iloc[0]["mean"] == 1.5
    assert report["numeric"].iloc[0]["std"] == pytest.approx(math.sqrt(0.5))
    assert report["missing"].iloc[0]["missing_count"] == 3
    assert "mixed" in report["categorical"]
    assert report["categorical"]["mixed"]["count"].sum() == 3
    with pytest.raises(AnalysisError, match="不是可统计"):
        numeric_statistics(frame, ["mixed"])


def test_no_numeric_boolean_date_and_all_empty_category():
    frame = pd.DataFrame({
        "text": ["A", "B"], "flag": [True, False],
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "empty": [None, ""],
    })
    report = analyze_dataframe(frame)
    assert report["numeric"].empty
    assert report["categorical"]["empty"].empty
    assert report["missing"].set_index("field").loc["empty", "missing_rate"] == 1


def test_single_valid_number_and_infinite_values():
    frame = pd.DataFrame({"value": [1.0, float("inf"), -float("inf"), None]})
    row = numeric_statistics(frame).iloc[0]
    assert row["count"] == 1
    assert row["mean"] == 1
    assert pd.isna(row["std"])
    assert missing_statistics(frame).iloc[0]["missing_count"] == 1


def test_empty_frames_and_undefined_rates():
    for frame in (pd.DataFrame(), pd.DataFrame({"x": pd.Series(dtype="Float64")})):
        report = analyze_dataframe(frame)
        assert report["overview"]["row_count"] == 0
        assert report["overview"]["missing_rate"] is None
        assert report["overview"]["duplicate_row_count"] == 0
        assert report["missing"]["missing_rate"].isna().all()
        assert preview_dataframe(frame).empty


def test_duplicate_and_blank_field_names():
    frame = pd.DataFrame([[1, 2, 3, 4]], columns=["x", "x", "x_2", None])
    result = prepare_dataframe(frame)
    assert list(result.columns) == ["x", "x_2", "x_2_2", "未命名字段_4"]
    assert list(field_info(frame)["field"]) == list(result.columns)


@pytest.mark.parametrize("limit", [20, 50, 100])
def test_preview_selection_and_row_limits(limit):
    frame = pd.DataFrame({"a": range(120), "b": range(120)})
    preview = preview_dataframe(frame, ["b"], limit)
    assert preview.shape == (limit, 1)
    assert preview.iloc[-1, 0] == limit - 1
    assert list(preview.columns) == ["b"]


@pytest.mark.parametrize("value", [None, [], {"a": [1]}])
def test_dataframe_required(value):
    with pytest.raises(AnalysisError, match="DataFrame"):
        analyze_dataframe(value)


def test_invalid_fields_limits_and_nested_values():
    frame = pd.DataFrame({"a": [1, 2], "category": ["a", "b"]})
    with pytest.raises(AnalysisError):
        preview_dataframe(frame, ["missing"])
    with pytest.raises(AnalysisError):
        preview_dataframe(frame, ["a", "a"])
    with pytest.raises(AnalysisError):
        preview_dataframe(frame, limit=10)
    with pytest.raises(AnalysisError):
        category_frequencies(frame, "a")
    with pytest.raises(AnalysisError):
        category_frequencies(frame, "category", 0)
    with pytest.raises(AnalysisError, match="嵌套"):
        analyze_dataframe(pd.DataFrame({"x": [[1], [2]]}))
    for nested in (pd.Series([1, 2]), pd.array([1, 2])):
        with pytest.raises(AnalysisError, match="嵌套"):
            analyze_dataframe(pd.DataFrame({"x": [nested]}))


def test_unused_categories_do_not_appear_in_frequencies():
    frame = pd.DataFrame({"group": pd.Categorical(["A", None], categories=["A", "B", ""])})
    assert category_frequencies(frame, "group").to_dict("records") == [{"value": "A", "count": 1}]


def test_different_missing_markers_are_equal_for_single_column_duplicates():
    frame = pd.DataFrame({"empty": [None, pd.NA, float("nan"), "", "  "]})
    assert missing_statistics(frame).iloc[0]["missing_count"] == 5
    assert duplicate_row_count(frame) == 4


def test_duration_values_are_not_silently_converted_to_numbers():
    frame = pd.DataFrame({"duration": pd.to_timedelta([1, 2], unit="D")})
    assert numeric_statistics(frame).empty
    assert field_info(frame).iloc[0]["dtype"] == "timedelta64[ns]"


def test_large_finite_numbers_do_not_overflow_mean_or_standard_deviation():
    constant = numeric_statistics(pd.DataFrame({"x": [1e308, 1e308]})).iloc[0]
    assert constant["mean"] == pytest.approx(1e308)
    assert constant["median"] == pytest.approx(1e308)
    assert constant["std"] == 0
    opposite = numeric_statistics(pd.DataFrame({"x": [-1e308, 1e308]})).iloc[0]
    assert opposite["mean"] == 0
    assert opposite["std"] == pytest.approx(2 ** 0.5 * 1e308)
    unrepresentable = numeric_statistics(pd.DataFrame({"x": [-1.7e308, 1.7e308]})).iloc[0]
    assert unrepresentable["mean"] == 0
    assert pd.isna(unrepresentable["std"])
