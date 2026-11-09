"""首页概览页面。"""

import sqlite3
from collections import Counter

import streamlit as st
import pandas as pd
import plotly.express as px

import config
from core.database import get_dashboard_stats
from core.file_service import FileService, FileServiceError
from ui.components import card, empty_state, format_size, metric_cards, page_header, style_figure


def render() -> None:
    page_header("dashboard")
    try:
        stats = get_dashboard_stats(db_path=config.DATABASE_PATH)
        records = FileService().list_files()
    except (OSError, sqlite3.Error, FileServiceError):
        st.error("文件概况读取失败，请检查数据库状态。")
        return
    st.badge("本地工作区", icon=":material/computer:", color="blue")
    metric_cards([
        ("files", "文件数量", stats["total_files"], "folder_open", "工作区已管理文件"),
        ("rows", "数据总行数", stats["total_rows"], "table_rows", "全部文件数据行数"),
        ("storage", "文件总存储空间", format_size(stats["total_size"]), "database", f"原始文件共 {stats['total_size']:,} 字节"),
        ("formats", "支持格式数量", len(config.SUPPORTED_EXTENSIONS), "description", "CSV / TSV / XLSX"),
    ])
    types = pd.DataFrame([
        {"文件类型": file_type.upper(), "文件数量": count}
        for file_type, count in stats["file_type_counts"].items()
    ])
    left, right = st.columns(2, gap="medium")
    with left, card("home_formats", height="stretch"):
        st.subheader("文件格式分布")
        st.caption("按上传格式查看文件构成")
        if records:
            figure = px.pie(types[types["文件数量"] > 0], names="文件类型", values="文件数量", hole=0.7)
            figure = style_figure(figure, title="File formats", height=285)
            figure.update_traces(textinfo="percent", textposition="inside", textfont_color="#FFFFFF", marker=dict(colors=["#496DE6", "#7C9AF0", "#2E9277"]))
            figure.add_annotation(x=0.5, y=0.5, text=f"{stats['total_files']}<br>files", showarrow=False, font=dict(size=20, color="#172B4D"))
            st.plotly_chart(figure, width="stretch", alt="实际上传文件的格式分布", key="home_format_chart")
        else:
            empty_state("暂无已上传文件，请先到文件管理导入数据。", "导入后将在此展示真实的文件格式分布。")
        with st.expander("查看格式明细"):
            st.dataframe(types, hide_index=True, key="home_types", alt="CSV、TSV、XLSX 文件数量")
    with right, card("home_categories", height="stretch"):
        st.subheader("文件分类分布")
        st.caption(f"当前共 {stats['category_count']} 个分类")
        if records:
            counts = Counter(record["category"] for record in records)
            categories = pd.DataFrame({"分类": list(counts), "文件数量": list(counts.values())})
            figure = px.bar(categories, x="文件数量", y="分类", orientation="h")
            st.plotly_chart(style_figure(figure, title="File categories", x_title="Files", y_title="Category", height=285), width="stretch", key="home_category_chart", alt="实际文件分类与数量")
        else:
            empty_state("暂无分类分布。", "为文件设置分类后，即可在此了解数据组织情况。")
    with card("home_recent"):
        st.subheader("最近上传文件")
        st.caption("最新 8 个文件 · 上传时间为 UTC · 概况来自已保存元数据")
        if records:
            st.dataframe([{"文件名称": record["display_name"], "类型": record["file_type"].upper(), "大小": format_size(record["file_size"]), "分类": record["category"], "上传时间（UTC）": record["created_at"]} for record in records[:8]], hide_index=True, key="home_recent", alt="最近上传文件的真实元数据")
        else:
            empty_state("还没有文件记录。", "从左侧“文件管理”开始，导入你的第一份数据文件。")
