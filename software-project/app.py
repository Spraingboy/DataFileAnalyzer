"""Streamlit 入口：初始化应用并提供六个页面导航。"""

import logging
import sqlite3

import streamlit as st

from config import APP_NAME, APP_VERSION, PAGE_TITLES, ensure_data_directories
from core.database import init_database
from ui import charts, dashboard, data_preview, export, file_manager, statistics
from ui.components import PAGE_ICONS, load_styles

logger = logging.getLogger(__name__)

PAGES = {
    PAGE_TITLES["dashboard"]: dashboard.render,
    PAGE_TITLES["file_manager"]: file_manager.render,
    PAGE_TITLES["data_preview"]: data_preview.render,
    PAGE_TITLES["statistics"]: statistics.render,
    PAGE_TITLES["charts"]: charts.render,
    PAGE_TITLES["export"]: export.render,
}


def main() -> None:
    st.set_page_config(page_title=f"DataFileAnalyzer · {APP_VERSION}", page_icon=":material/analytics:", layout="wide")
    load_styles()
    try:
        ensure_data_directories()
        init_database()
    except (OSError, sqlite3.Error):
        logger.exception("初始化数据目录或数据库失败")
        st.error("初始化失败，请检查 data 目录的读写权限，以及数据库是否被占用。")
        st.stop()

    with st.sidebar:
        st.html(f'<div class="dfa-brand"><span class="dfa-mark">D</span><div><div class="dfa-brand-name">DataFileAnalyzer</div><div class="dfa-brand-cn">{APP_NAME}</div></div></div>')
        st.html('<div class="dfa-section-label">WORKSPACE / 数据工作区</div>')
    legacy = {"首页概览": "系统概览", "图表可视化": "数据可视化"}
    current = st.session_state.get("page_navigation")
    if current in legacy:
        st.session_state["page_navigation"] = legacy[current]
    icons = {title: PAGE_ICONS[key] for key, title in PAGE_TITLES.items()}
    page = st.sidebar.radio("页面导航", list(PAGES), format_func=lambda title: f":material/{icons[title]}: {title}", key="page_navigation", label_visibility="collapsed", width="stretch")
    if st.session_state.get("active_page") != page:
        # 跨页不延续删除意图或旧下载，避免返回页面后误操作。
        st.session_state["fm_pending_delete"] = None
        st.session_state.pop("export_ready", None)
        st.session_state["active_page"] = page
    with st.sidebar:
        st.html(f'<div class="dfa-sidebar-footer">DataFileAnalyzer {APP_VERSION}<br>本地运行 · 数据保存在此设备</div>')
    PAGES[page]()


if __name__ == "__main__":
    main()
