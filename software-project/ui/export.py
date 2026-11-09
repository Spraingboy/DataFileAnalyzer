"""数据下载中心；保持既有导出函数与结果不变。"""

from hashlib import sha256
from pathlib import PureWindowsPath
import re

import streamlit as st

from core.analysis_service import AnalysisError, prepare_dataframe
from core.data_reader import DataReadError, read_data
from core.export_service import (
    ExportError, export_missing_statistics, export_numeric_statistics,
    export_selected_csv, export_selected_xlsx,
)
from ui.analysis_page import select_dataset
from ui.components import card, empty_state, format_size, page_header

EXPORT_TYPES = ("所选列 CSV", "所选列 XLSX", "数值统计 CSV", "缺失值统计 CSV")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def _raw_frame(content, file_type):
    return read_data(content, file_type).frame


@st.cache_data(ttl=300, max_entries=4, show_spinner=False)
def _export_bytes(content, file_type, columns, kind):
    functions = {
        EXPORT_TYPES[0]: export_selected_csv, EXPORT_TYPES[1]: export_selected_xlsx,
        EXPORT_TYPES[2]: export_numeric_statistics, EXPORT_TYPES[3]: export_missing_statistics,
    }
    return functions[kind](_raw_frame(content, file_type), columns)


def render() -> None:
    page_header("export")
    selected = select_dataset("export", parse=False)
    if selected is None:
        st.session_state.pop("export_ready", None)
        return
    record, content, _ = selected
    name = re.sub(r"[\x00-\x1f\x7f]", "_", PureWindowsPath(record["original_name"]).name) or f"file_{record['id']}.{record['file_type']}"
    left, right = st.columns([1, 2], gap="medium")
    with left, card("export_original"):
        st.subheader(":material/description: 原始文件")
        st.caption("保留原始编码和完整文件内容")
        st.write(name)
        st.badge(record["file_type"].upper(), color="blue")
        st.caption(f"{format_size(len(content))} · 导入时 {record['row_count']} 行 / {record['column_count']} 列")
        if content:
            st.download_button(
                "下载原始文件", content, file_name=name,
                mime={"csv": "text/csv", "tsv": "text/tab-separated-values", "xlsx": XLSX_MIME}[record["file_type"]],
                key=f"export_original_{record['id']}", icon=":material/download:", width="stretch",
            )
        else:
            st.warning("原始文件为空，没有可下载内容。")
    with right, card("export_derived"):
        st.subheader(":material/download: 数据与统计结果")
        try:
            frame = _raw_frame(content, record["file_type"])
            names = list(prepare_dataframe(frame).columns)
        except (DataReadError, AnalysisError) as exc:
            st.session_state.pop("export_ready", None)
            st.error(str(exc))
            return
        st.caption(f"当前文件实际规模：{len(frame):,} 行 × {len(frame.columns)} 列")
        columns_key = f"export_columns_{record['id']}"
        if columns_key in st.session_state:
            previous = st.session_state[columns_key]
            if any(column not in names for column in previous):
                st.session_state[columns_key] = [column for column in previous if column in names]
        columns = st.multiselect(
            "选择导出字段（按选择顺序导出）", names, default=names, key=columns_key,
            persist_state="session", wrap=False,
        )
        kind = st.selectbox("导出类型", list(EXPORT_TYPES), key="export_kind", persist_state="session")
        st.caption("导出范围为所选字段的全部记录，不使用图表抽样。选列文件保留原始单元格值；统计沿用统计分析口径。")
        identity = (record["id"], sha256(content).hexdigest(), tuple(columns), kind)
        if st.session_state.get("export_ready", {}).get("identity") != identity:
            st.session_state.pop("export_ready", None)
        if not columns:
            empty_state("请至少选择一个导出字段。")
            return
        suffix = kind.replace(" CSV", "").replace(" XLSX", "")
        extension = "xlsx" if kind == EXPORT_TYPES[1] else "csv"
        filename = f"{PureWindowsPath(name).stem}_{record['id']}_{suffix}.{extension}"
        st.caption(f"将生成：{filename} · 所选 {len(columns)} 个字段 / 全部 {len(frame):,} 条记录")
        if st.button("生成下载文件", key="export_generate", type="primary", icon=":material/file_export:"):
            try:
                with st.spinner("正在生成导出文件…"):
                    payload = _export_bytes(content, record["file_type"], tuple(columns), kind)
                st.session_state["export_ready"] = {"identity": identity, "payload": payload}
            except (ExportError, AnalysisError, DataReadError) as exc:
                st.session_state.pop("export_ready", None)
                st.error(str(exc))
        ready = st.session_state.get("export_ready")
        if ready:
            st.success("导出文件已准备就绪。", icon=":material/check_circle:")
            st.download_button(
                "下载生成文件", ready["payload"], file_name=filename,
                mime=XLSX_MIME if extension == "xlsx" else "text/csv;charset=utf-8",
                key="export_download", icon=":material/download:", width="stretch",
            )
    with card("export_help"):
        st.subheader("如何选择导出格式")
        st.caption("原始文件：继续使用原始编码或完整 Excel 工作簿。CSV：轻量、通用，使用 UTF-8-SIG 保存中文。XLSX：在 Excel 中浏览所选字段。")
        st.caption("数值统计：均值、中位数、标准差等完整结果。缺失值统计：各字段缺失数量与 0～1 比例。更换文件、字段或格式后，需要重新生成下载文件。")

