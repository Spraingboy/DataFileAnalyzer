"""数据预览和统计页面共用逻辑，兼容既有页面 render() 入口。"""

import pandas as pd
import streamlit as st
import config

from core.analysis_service import (
    AnalysisError, analyze_dataframe, field_info, prepare_dataframe, preview_dataframe,
)
from core.data_reader import DataReadError, read_data
from core.dataset_service import DatasetLoadError, load_uploaded_file
from core.file_service import FileService, FileServiceError
from ui.components import card, empty_state, format_size, metric_cards, page_header


@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def _cached_frame(content: bytes, file_type: str) -> pd.DataFrame:
    return prepare_dataframe(read_data(content, file_type).frame)


@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def _cached_report(content: bytes, file_type: str) -> dict:
    # 用完整原始字节作为缓存键，避免大表抽样哈希漏掉内容变化。
    return analyze_dataframe(_cached_frame(content, file_type))


def select_dataset(prefix, *, parse=True):
    try:
        records = FileService().list_files()
        if not records:
            empty_state("暂无已上传文件，请先到文件管理导入数据。", "支持 CSV、TSV、XLSX；导入后即可在这里继续工作。")
            return None
        by_id = {record["id"]: record for record in records}
        key = f"{prefix}_file"
        if st.session_state.get(key) not in by_id:
            st.session_state[key] = records[0]["id"]
        with card(f"{prefix}_dataset"):
            file_id = st.selectbox(
                "选择已上传文件", list(by_id), key=key, persist_state="session",
                format_func=lambda value: f"{by_id[value]['display_name']}（ID {value}）",
            )
            # 每次检查实际文件，再查缓存；保留文件选择但不保留过期数据。
            record, content = load_uploaded_file(file_id)
            frame = None
            if parse:
                with st.spinner("正在读取数据…"):
                    frame = _cached_frame(content, record["file_type"])
            with st.container(horizontal=True, vertical_alignment="center"):
                st.badge(record["file_type"].upper(), color="blue")
                st.caption(f"当前文件：{record['display_name']} · {format_size(len(content))}" + (f" · {len(frame)} 行 / {len(frame.columns)} 列" if frame is not None else ""))
        return record, content, frame
    except (FileServiceError, DatasetLoadError, DataReadError, AnalysisError) as exc:
        st.error(str(exc))
        return None


# 保留阶段三内部入口，供原有页面及测试兼容使用。
_select_dataset = select_dataset
cached_dataframe = _cached_frame


def render_preview() -> None:
    page_header("data_preview")
    selected = _select_dataset("preview")
    if selected is None:
        return
    record, _, frame = selected
    st.caption(f"实际数据：{len(frame)} 行、{len(frame.columns)} 列；Excel 仅使用第一张工作表。")
    fields = field_info(frame)
    numbers = int(fields["numeric"].sum())
    metric_cards([
        ("preview_rows", "数据行数", len(frame), "table_rows", "完整数据集记录数"),
        ("preview_fields", "字段数量", len(frame.columns), "view_column", "全部数据字段"),
        ("preview_numeric", "数值字段", numbers, "numbers", "可进行数值统计"),
        ("preview_other", "非数值字段", len(frame.columns) - numbers, "label", "分类、日期等字段"),
    ])
    with card("preview_table"):
        st.subheader("数据记录")
        tools = st.columns([1, 2.7], gap="medium", vertical_alignment="bottom")
        with tools[0]:
            limit = st.segmented_control("预览行数", [20, 50, 100], default=20, required=True, key="preview_limit", persist_state="session")
        columns_key = f"preview_columns_{record['id']}"
        if columns_key in st.session_state:
            st.session_state[columns_key] = [name for name in st.session_state[columns_key] if name in frame.columns]
        with tools[1]:
            columns = st.multiselect("选择预览字段", list(frame.columns), default=list(frame.columns), key=columns_key, persist_state="session", wrap=False)
        if not columns:
            empty_state("请至少选择一个字段进行预览。")
        else:
            try:
                st.dataframe(preview_dataframe(frame, columns, limit), hide_index=True, key="preview_data", height=min(420, 38 + min(limit, len(frame)) * 32), alt=f"所选字段的前 {limit} 行数据")
                st.caption(f"展示前 {min(limit, len(frame))} 行 · 已选择 {len(columns)} / {len(frame.columns)} 个字段")
            except AnalysisError as exc:
                st.error(str(exc))
    with card("preview_fields"):
        st.subheader("字段信息")
        st.caption("空白按缺失处理，整列可解析的数值文本自动识别；重复或空白表头生成唯一名称。")
        st.dataframe(fields.rename(columns={"field": "字段", "dtype": "类型", "numeric": "数值字段"}), hide_index=True, key="preview_fields", height=min(280, 38 + len(fields) * 32), alt="所选数据文件的字段名称和类型")


def render_analysis() -> None:
    page_header("statistics")
    selected = _select_dataset("analysis")
    if selected is None:
        return
    record, content, _ = selected
    try:
        with st.spinner("正在统计实际数据…"):
            report = _cached_report(content, record["file_type"])
    except AnalysisError as exc:
        st.error(str(exc))
        return
    overview = report["overview"]
    metric_cards([
        ("analysis_rows", "总行数", overview["row_count"], "table_rows", "统计覆盖全部记录"),
        ("analysis_columns", "总列数", overview["column_count"], "view_column", "当前数据集字段"),
        ("analysis_missing", "缺失值数量", overview["missing_count"], "data_alert", "全部缺失单元格"),
        ("analysis_duplicates", "重复行数量", overview["duplicate_row_count"], "content_copy", "首次出现以外的重复行"),
    ])
    with st.expander("查看完整数据概况"):
        st.dataframe(pd.DataFrame([
        {"指标": "数据行数", "值": str(overview["row_count"])},
        {"指标": "字段数量", "值": str(overview["column_count"])},
        {"指标": "数值字段数量", "值": str(overview["numeric_column_count"])},
        {"指标": "缺失单元格数量", "值": str(overview["missing_count"])},
        {"指标": "整体缺失率", "值": _rate(overview["missing_rate"])},
        {"指标": "重复行数", "值": str(overview["duplicate_row_count"])},
        ]), hide_index=True, key="analysis_overview", alt="数据规模、缺失值和重复行的整体概况")

    numeric_tab, missing_tab, duplicate_tab, category_tab = st.tabs(["数值统计", "缺失值分析", "重复值分析", "分类频次分析"], key="analysis_tabs")
    with numeric_tab, card("analysis_numeric"):
        st.subheader("数值字段统计")
        st.caption("有效值仅计有限数值；标准差为样本标准差（ddof=1），不足两项时为空。混合文本列按分类字段处理。")
        if report["numeric"].empty:
            empty_state("该文件没有可统计的数值字段，仍可查看缺失值和分类频次。")
        else:
            st.dataframe(report["numeric"].rename(columns={
            "field": "字段", "count": "有效值数量", "mean": "均值", "median": "中位数",
            "max": "最大值", "min": "最小值", "std": "标准差",
            }), hide_index=True, key="numeric_statistics", column_config={label: st.column_config.NumberColumn(format="%.6g") for label in ("均值", "中位数", "最大值", "最小值", "标准差")}, alt="各数值字段的有效数量和描述统计")

    with missing_tab, card("analysis_missing"):
        st.subheader("缺失值分析")
        missing = report["missing"].copy()
        missing["missing_rate"] = missing["missing_rate"].map(_rate)
        st.dataframe(missing.rename(columns={
        "field": "字段", "missing_count": "缺失数量", "missing_rate": "缺失率",
        }), hide_index=True, key="missing_statistics", alt="各字段的缺失数量与缺失率")
        st.caption("缺失率以全部数据行为分母，按百分比保留两位小数展示。")
    with duplicate_tab, card("analysis_duplicates"):
        st.subheader("重复值分析")
        st.metric("额外重复行", overview["duplicate_row_count"])
        st.caption("按规范化后的完整行判重，首次出现的记录不计入重复数量；没有修改或移除源数据。")

    with category_tab, card("analysis_categories"):
        st.subheader("分类字段前 10 项频次")
        categories = report["categorical"]
        if not categories:
            empty_state("该文件没有分类字段。")
            return
        key = f"analysis_category_{record['id']}"
        if st.session_state.get(key) not in categories:
            st.session_state[key] = next(iter(categories))
        field = st.selectbox("选择分类字段", list(categories), key=key, persist_state="session")
        frequencies = categories[field]
        if frequencies.empty:
            empty_state("该字段全部为空，没有可统计的分类值。")
        else:
            st.dataframe(frequencies.rename(columns={"value": "分类值", "count": "频次"}), hide_index=True, key="category_statistics", alt=f"字段 {field} 中频次最高的前 10 项，缺失值不参与")


def _rate(value):
    return f"{value:.2%}" if value is not None and pd.notna(value) else "—"
