"""统一展示组件；只格式化显示，不更改业务数据或计算结果。"""

from html import escape
from pathlib import Path

import streamlit as st

import config

PALETTE = ["#496DE6", "#7C9AF0", "#2E9277", "#8B7BC8", "#E6A23C", "#62A5BC"]
PAGE_ICONS = {"dashboard": "space_dashboard", "file_manager": "folder_open", "data_preview": "table_view", "statistics": "query_stats", "charts": "bar_chart", "export": "download"}
DESCRIPTIONS = {
    "dashboard": "集中管理多格式数据，快速了解工作区的数据规模与文件分布。",
    "file_manager": "导入、归类与维护数据文件，让每一份数据井然有序。",
    "data_preview": "浏览数据记录与字段结构，为接下来的分析做好准备。",
    "statistics": "对完整数据进行描述性统计、缺失值检测和质量分析。",
    "charts": "选择合适的图表与字段，直观探索数据分布与变化关系。",
    "export": "下载原始文件、所选数据或统计结果，继续你的分析工作。",
}


def load_styles() -> None:
    css = (Path(config.BASE_DIR) / "assets" / "styles.css").read_text(encoding="utf-8")
    st.html(f"<style>{css}</style>")


def page_header(page: str) -> None:
    st.html('<div class="dfa-kicker">DATA WORKSPACE</div>')
    st.title(config.PAGE_TITLES[page])
    st.caption(DESCRIPTIONS[page])


def card(key: str, *, height="content"):
    return st.container(border=False, key=f"card_{key}", height=height)


def empty_state(message: str, detail: str = "") -> None:
    st.info(message, icon=":material/info:")
    if detail:
        st.html(f'<div class="dfa-empty">{escape(detail)}</div>')


def format_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{int(amount)} B" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return "0 B"


def metric_cards(items) -> None:
    with st.container(horizontal=True, gap="medium", key=f"kpi_{items[0][0]}"):
        for key, label, value, icon, note in items:
            with st.container(width="stretch", height="stretch", key=f"card_metric_{key}"):
                st.metric(label, value, help=note)
                st.caption(f":material/{icon}: {note}")


def style_figure(figure, *, title=None, x_title=None, y_title=None, height=370):
    """复制 Figure，仅调整外观；点位、分箱与频次保持原样。"""
    styled = type(figure)(figure)
    styled.update_layout(
        template="plotly_white", paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        colorway=PALETTE, height=height, margin=dict(l=20, r=20, t=52, b=30),
        font=dict(family="Segoe UI, Microsoft YaHei, sans-serif", size=12, color="#344054"),
        title=dict(text=title if title is not None else figure.layout.title.text, font=dict(size=16, color="#172B4D"), x=0.01),
        legend=dict(orientation="h", y=-0.15, title_text=""),
    )
    styled.update_xaxes(showgrid=False, linecolor="#E4EAF3", zeroline=False)
    styled.update_yaxes(gridcolor="#EEF2F8", linecolor="#E4EAF3", zeroline=False)
    if x_title is not None:
        styled.update_xaxes(title_text=x_title)
    if y_title is not None:
        styled.update_yaxes(title_text=y_title)
    for trace in styled.data:
        if trace.type in ("bar", "histogram"):
            trace.update(marker_color=PALETTE[0], marker_line_width=0, opacity=0.9)
        elif trace.type in ("scatter", "scattergl"):
            trace.update(marker=dict(color=PALETTE[0], size=6, opacity=0.75), line=dict(color=PALETTE[0], width=2))
    return styled
