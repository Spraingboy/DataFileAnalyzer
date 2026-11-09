"""Plotly Express 图表与绘图抽样；不修改源表或统计结果。"""

from dataclasses import dataclass

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from core.analysis_service import category_frequencies, field_info, prepare_dataframe

MAX_CHART_POINTS = 2000
CHART_TYPES = ("分类频次柱状图", "记录顺序折线图", "数值分布直方图", "双数值散点图")


class ChartError(ValueError):
    """字段不适用或没有可绘制的有效数据。"""


@dataclass
class ChartResult:
    figure: Figure
    valid_rows: int
    point_count: int
    sampled: bool = False


def _finite(series):
    return series.notna() & ~series.isin([float("inf"), -float("inf")])


def chart_fields(frame: pd.DataFrame) -> dict[str, list[str]]:
    data = prepare_dataframe(frame)
    info = field_info(data)
    numeric = info.loc[info["numeric"], "field"].tolist()
    return {
        "numeric": [name for name in numeric if _finite(data[name]).any()],
        "categorical": [name for name in data.columns if name not in numeric and data[name].notna().any()],
    }


def scatter_y_fields(frame: pd.DataFrame, x: str) -> list[str]:
    data = prepare_dataframe(frame)
    numeric = chart_fields(data)["numeric"]
    if x not in numeric:
        return []
    return [name for name in numeric if name != x and (_finite(data[x]) & _finite(data[name])).any()]


def _sample(data: pd.DataFrame) -> pd.DataFrame:
    if len(data) <= MAX_CHART_POINTS:
        return data.copy()
    # 确定性的等间隔位置抽样，包含首尾记录并保持原顺序。
    positions = [index * (len(data) - 1) // (MAX_CHART_POINTS - 1) for index in range(MAX_CHART_POINTS)]
    return data.iloc[positions].copy()


def build_chart(frame: pd.DataFrame, chart_type: str, x: str, y: str | None = None) -> ChartResult:
    data = prepare_dataframe(frame)
    if chart_type not in CHART_TYPES:
        raise ChartError("不支持的图表类型。")
    fields = chart_fields(data)
    if chart_type == CHART_TYPES[0]:
        if x not in fields["categorical"]:
            raise ChartError("请选择包含有效值的分类字段。")
        counts = category_frequencies(data, x, top_n=max(len(data), 1))
        figure = px.bar(counts, x="value", y="count", labels={"value": x, "count": "频次"}, title=f"{x} 的分类频次")
        figure.update_xaxes(type="category")
        return ChartResult(figure, int(counts["count"].sum()), len(counts))

    if x not in fields["numeric"]:
        raise ChartError("请选择包含有限数值的数值字段。")
    order = pd.Series(range(1, len(data) + 1), index=data.index)
    if chart_type == CHART_TYPES[3]:
        if y not in scatter_y_fields(data, x):
            raise ChartError("散点图需要两个不同的数值字段，并且至少有一对同时有效的值。")
        mask = _finite(data[x]) & _finite(data[y])
        points = pd.DataFrame({"_x": data.loc[mask, x].to_numpy(), "_y": data.loc[mask, y].to_numpy(), "_record": order.loc[mask].to_numpy()})
        sampled = _sample(points)
        figure = px.scatter(sampled, x="_x", y="_y", hover_data=["_record"], labels={"_x": x, "_y": y, "_record": "记录序号"}, title=f"{x} 与 {y} 的散点图")
        return ChartResult(figure, len(points), len(sampled), len(sampled) < len(points))

    mask = _finite(data[x])
    points = pd.DataFrame({"_value": data.loc[mask, x].to_numpy(), "_record": order.loc[mask].to_numpy()})
    if chart_type == CHART_TYPES[1]:
        sampled = _sample(points)
        figure = px.line(sampled, x="_record", y="_value", markers=len(sampled) == 1, labels={"_record": "记录序号", "_value": x}, title=f"{x} 按记录顺序变化")
        return ChartResult(figure, len(points), len(sampled), len(sampled) < len(points))
    figure = px.histogram(points, x="_value", nbins=30, labels={"_value": x}, title=f"{x} 的数值分布")
    figure.update_yaxes(title_text="频次")
    return ChartResult(figure, len(points), len(points))
