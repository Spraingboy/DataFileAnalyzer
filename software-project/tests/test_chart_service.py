"""核对四种图表的数据来源、字段限制及等间隔抽样。"""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from core.analysis_service import numeric_statistics
from core.chart_service import CHART_TYPES, ChartError, build_chart, chart_fields, scatter_y_fields


def test_bar_counts_all_categories_from_full_data():
    frame = pd.DataFrame({"group": ["A"] * 3000 + ["B"] * 1000 + [None]})
    result = build_chart(frame, CHART_TYPES[0], "group")
    assert list(result.figure.data[0].x) == ["A", "B"]
    assert list(result.figure.data[0].y) == [3000, 1000]
    assert result.valid_rows == 4000
    assert result.point_count == 2
    assert not result.sampled
    many = pd.DataFrame({"group": [f"类别_{n}" for n in range(30)]})
    assert build_chart(many, CHART_TYPES[0], "group").point_count == 30


@pytest.mark.parametrize("rows", [1999, 2000, 2001, 5000])
@pytest.mark.parametrize("kind", [CHART_TYPES[1], CHART_TYPES[3]])
def test_even_sampling_boundaries_keep_endpoints_and_order(rows, kind):
    frame = pd.DataFrame({"x": range(rows), "y": [n * 2 for n in range(rows)]})
    original = frame.copy(deep=True)
    result = build_chart(frame, kind, "x", "y" if kind == CHART_TYPES[3] else None)
    assert result.point_count == min(rows, 2000)
    assert result.valid_rows == rows
    assert result.sampled == (rows > 2000)
    trace = result.figure.data[0]
    positions = list(trace.x)
    expected = list(range(rows)) if rows <= 2000 else [i * (rows - 1) // 1999 for i in range(2000)]
    if kind == CHART_TYPES[1]:
        assert positions == [i + 1 for i in expected]
        assert list(trace.y) == expected
    else:
        assert positions == expected
        assert list(trace.y) == [i * 2 for i in expected]
    assert_frame_equal(frame, original)
    # 图表抽样不得改变统计函数的全量计数与均值。
    stats = numeric_statistics(frame).set_index("field")
    assert stats.loc["x", "count"] == rows
    assert stats.loc["x", "mean"] == pytest.approx((rows - 1) / 2)


def test_histogram_uses_all_finite_values():
    frame = pd.DataFrame({"x": [*range(3000), None, float("inf"), -float("inf")]})
    result = build_chart(frame, CHART_TYPES[2], "x")
    assert result.figure.data[0].type == "histogram"
    assert len(result.figure.data[0].x) == 3000
    assert not result.sampled


def test_line_uses_record_position_not_index_labels():
    frame = pd.DataFrame({"x": [1, None, 3, float("inf"), 5]}, index=[9, 9, 2, 7, 0])
    result = build_chart(frame, CHART_TYPES[1], "x")
    assert list(result.figure.data[0].x) == [1, 3, 5]
    assert list(result.figure.data[0].y) == [1, 3, 5]


def test_scatter_only_uses_joint_finite_rows():
    frame = pd.DataFrame({"x": [1, None, 3, 4], "y": [None, 2, 6, float("inf")]})
    result = build_chart(frame, CHART_TYPES[3], "x", "y")
    assert result.valid_rows == 1
    assert list(result.figure.data[0].x) == [3]
    assert list(result.figure.data[0].y) == [6]


def test_fields_exclude_invalid_types_and_empty_values():
    frame = pd.DataFrame({
        "number": [1, 2], "group": ["A", "B"], "empty": [None, None],
        "flag": [True, False], "infinity": [float("inf"), -float("inf")],
    })
    assert chart_fields(frame) == {"numeric": ["number"], "categorical": ["group", "flag"]}
    assert scatter_y_fields(frame, "number") == []


@pytest.mark.parametrize("kind,x,y", [
    (CHART_TYPES[0], "number", None), (CHART_TYPES[1], "group", None),
    (CHART_TYPES[2], "empty", None), (CHART_TYPES[3], "number", "number"),
    (CHART_TYPES[3], "number", "group"), ("不支持", "number", None),
])
def test_invalid_fields_are_rejected(kind, x, y):
    frame = pd.DataFrame({"number": [1, 2], "group": ["a", "b"], "empty": [None, None]})
    with pytest.raises(ChartError):
        build_chart(frame, kind, x, y)


def test_scatter_without_overlapping_valid_rows_is_rejected():
    frame = pd.DataFrame({"x": [1, None], "y": [None, 2]})
    assert scatter_y_fields(frame, "x") == []
    with pytest.raises(ChartError):
        build_chart(frame, CHART_TYPES[3], "x", "y")
