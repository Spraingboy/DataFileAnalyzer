"""数据可视化页面；图表数据与抽样仍由既有 chart_service 生成。"""

import streamlit as st

from core.analysis_service import AnalysisError
from core.chart_service import CHART_TYPES, ChartError, build_chart, chart_fields, scatter_y_fields
from ui.analysis_page import cached_dataframe, select_dataset
from ui.components import card, empty_state, page_header, style_figure


@st.cache_data(ttl=300, max_entries=4, show_spinner=False)
def _cached_chart(content, file_type, chart_type, x, y):
    return build_chart(cached_dataframe(content, file_type), chart_type, x, y)


def _field(label, options, key):
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    return st.selectbox(label, options, key=key, persist_state="session")


def render() -> None:
    page_header("charts")
    selected = select_dataset("chart")
    if selected is None:
        return
    record, content, frame = selected
    fields = chart_fields(frame)
    with card("chart_controls"):
        st.subheader("图表配置")
        controls = st.columns([1.2, 2], gap="medium")
        with controls[0]:
            kind = st.selectbox("图表类型", list(CHART_TYPES), key="chart_type", persist_state="session")
        options = fields["categorical"] if kind == CHART_TYPES[0] else fields["numeric"]
        if not options:
            empty_state("当前文件没有适用的有效分类字段。" if kind == CHART_TYPES[0] else "当前文件没有包含有限数值的数值字段。", "请选择其他图表类型或数据文件。")
            return
        y = None
        with controls[1]:
            if kind == CHART_TYPES[3]:
                axes = st.columns(2, gap="medium")
                with axes[0]:
                    x = _field("数值字段（X）", options, f"chart_x_{record['id']}_{kind}")
                y_options = scatter_y_fields(frame, x)
                if not y_options:
                    empty_state("没有与该字段同时有效的另一数值字段，请更换 X 字段或图表类型。")
                    return
                with axes[1]:
                    y = _field("数值字段（Y）", y_options, f"chart_y_{record['id']}_{x}")
            else:
                x = _field("分类字段" if kind == CHART_TYPES[0] else "数值字段", options, f"chart_x_{record['id']}_{kind}")
    descriptions = {
        CHART_TYPES[0]: ("Category frequency", "Category", "Frequency", "比较不同分类在全部数据中的出现次数。"),
        CHART_TYPES[1]: ("Record trend", "Record", "Value", "按原始记录顺序观察数值变化，不对记录重新排序。"),
        CHART_TYPES[2]: ("Value distribution", "Value", "Frequency", "通过直方图了解数值的集中程度与分布形态。"),
        CHART_TYPES[3]: ("Numeric relationship", "X value", "Y value", "通过成对有效数值观察两个字段的关系。"),
    }
    title, x_title, y_title, purpose = descriptions[kind]
    try:
        with st.spinner("正在生成图表…"):
            result = _cached_chart(content, record["file_type"], kind, x, y)
        figure = style_figure(result.figure, title=title, x_title=x_title, y_title=y_title, height=440)
        if kind == CHART_TYPES[0]:
            figure.update_traces(hovertemplate="Category: %{x}<br>Frequency: %{y}<extra></extra>")
        elif kind == CHART_TYPES[1]:
            figure.update_traces(hovertemplate="Record: %{x}<br>Value: %{y}<extra></extra>")
        elif kind == CHART_TYPES[3]:
            figure.update_traces(hovertemplate="X: %{x}<br>Y: %{y}<br>Record: %{customdata[0]}<extra></extra>")
        with card("chart_canvas"):
            st.plotly_chart(figure, width="stretch", theme=None, key="data_chart", alt=f"{kind}：{x}" + (f" 与 {y}" if y else ""))
        with card("chart_notes"):
            st.subheader("图表说明")
            st.caption(f"{kind} · 字段：{x}" + (f" / {y}" if y else ""))
            st.write(purpose)
            if result.sampled:
                st.caption(f"共有 {result.valid_rows} 条有效记录，等间隔抽样展示 {result.point_count} 条；统计和导出仍使用全部记录。")
            elif kind == CHART_TYPES[0]:
                st.caption(f"基于全部 {result.valid_rows} 条非缺失记录，展示 {result.point_count} 个分类的频次。")
            else:
                st.caption(f"基于全部 {result.valid_rows} 条有效记录绘制，未抽样。")
            st.caption("数值图排除缺失值与正负无穷；折线横轴保留原始记录序号，散点图仅保留成对有效数值。")
    except (ChartError, AnalysisError) as exc:
        st.error(str(exc))

