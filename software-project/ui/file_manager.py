"""文件导入与管理界面；业务操作继续由现有 FileService 负责。"""

import streamlit as st

import config
from core.file_service import FileService, FileServiceError
from ui.components import card, empty_state, format_size, page_header


def _notice(message):
    st.session_state["fm_notice"] = message
    st.rerun()


def render() -> None:
    page_header("file_manager")
    service = FileService()
    st.session_state.setdefault("fm_upload_version", 0)
    st.session_state.setdefault("fm_pending_delete", None)
    message = st.session_state.pop("fm_notice", None)
    if message:
        st.success(message, icon=":material/check_circle:")

    version = st.session_state["fm_upload_version"]
    with card("file_upload"):
        st.subheader(":material/upload_file: 导入数据文件")
        with st.form(f"fm_import_{version}", border=False):
            left, right = st.columns([1, 1.35], gap="large")
            with left:
                uploaded = st.file_uploader(
                    "选择文件", type=list(config.SUPPORTED_EXTENSIONS),
                    accept_multiple_files=False, max_upload_size=config.MAX_FILE_SIZE_MB,
                    key=f"fm_upload_{version}",
                )
                st.caption("CSV / TSV / XLSX · 单文件 10MB")
                st.caption("最多 50000 数据行、100 列；首行为表头。")
            with right:
                names = st.columns(2, gap="medium")
                with names[0]:
                    display_name = st.text_input("展示名称（可选）", placeholder="默认使用原始名称", key=f"fm_name_{version}")
                with names[1]:
                    category = st.text_input("分类（可选）", placeholder="未分类", key=f"fm_category_{version}")
                description = st.text_area("备注", placeholder="为这份数据添加简短说明", height=80, key=f"fm_description_{version}")
            submitted = st.form_submit_button("导入文件", type="primary", icon=":material/upload:")
        if submitted:
            if uploaded is None:
                st.error("请先选择一个文件。")
            else:
                try:
                    with st.spinner("正在校验并保存文件…"):
                        service.import_file(
                            uploaded.name, uploaded.getvalue(), display_name=display_name,
                            category=category, description=description,
                        )
                    st.session_state["fm_upload_version"] += 1
                    _notice("文件导入成功。")
                except FileServiceError as exc:
                    st.error(str(exc))

    with card("file_library"):
        st.subheader("文件库")
        try:
            all_records = service.list_files()
            tools = st.columns([2, 1, 1], gap="medium", vertical_alignment="bottom")
            with tools[0]:
                keyword = st.text_input("搜索文件", placeholder="搜索原始名称或展示名称", key="fm_search", persist_state="session")
            with tools[1]:
                file_type = st.selectbox(
                    "文件类型", [None, *config.SUPPORTED_EXTENSIONS],
                    format_func=lambda value: "全部类型" if value is None else value.upper(),
                    key="fm_type_filter", persist_state="session",
                )
            options = [None, *sorted({record["category"] for record in all_records})]
            if st.session_state.get("fm_category_filter") not in options:
                st.session_state["fm_category_filter"] = None
            with tools[2]:
                selected_category = st.selectbox(
                    "分类筛选", options, key="fm_category_filter", persist_state="session",
                    format_func=lambda value: "全部分类" if value is None else value,
                )
            records = service.list_files(keyword, selected_category, file_type)
        except FileServiceError as exc:
            st.error(str(exc))
            return
        if not records:
            st.session_state["fm_pending_delete"] = None
            empty_state("暂无符合条件的文件。", "可调整搜索与筛选条件，或在上方导入 CSV、TSV、XLSX 文件。")
            return
        st.caption(f"共 {len(records)} 个文件 · 上传时间为 UTC")
        columns = {
            "id": "ID", "original_name": "原始名称", "display_name": "展示名称",
            "file_type": "类型", "file_size": "大小（字节）", "row_count": "数据行数",
            "column_count": "列数", "category": "分类", "description": "备注", "created_at": "上传时间（UTC）",
        }
        rows = [{label: record[field] for field, label in columns.items()} for record in records]
        for row in rows:
            row["类型"] = row["类型"].upper()
            row["大小"] = format_size(row["大小（字节）"])
        st.dataframe(
            rows, hide_index=True, key="file_library", height=min(360, 38 + 35 * len(records)),
            column_order=["展示名称", "类型", "大小", "数据行数", "分类", "上传时间（UTC）"],
            column_config={
                "展示名称": st.column_config.TextColumn(width="large", pinned=True),
                "类型": st.column_config.TextColumn(width="small"),
                "大小": st.column_config.TextColumn(width="small"),
                "数据行数": st.column_config.NumberColumn(format="%d"),
            },
            alt="已导入文件的元数据列表",
        )

    with card("file_actions"):
        st.subheader(":material/edit_document: 文件操作")
        by_id = {record["id"]: record for record in records}
        if st.session_state.get("fm_selected") not in by_id:
            st.session_state["fm_selected"] = records[0]["id"]
        selected_id = st.selectbox(
            "选择要管理的文件", list(by_id), key="fm_selected", persist_state="session",
            format_func=lambda value: f"{by_id[value]['display_name']}（ID {value}）",
        )
        record = by_id[selected_id]
        st.caption(f"原始名称：{record['original_name']} · {format_size(record['file_size'])} · {record['row_count']} 行 / {record['column_count']} 列")
        if st.session_state["fm_pending_delete"] != selected_id:
            st.session_state["fm_pending_delete"] = None
        snapshot = tuple(record[field] for field in ("id", "display_name", "category", "description", "updated_at"))
        changed = st.session_state.get("fm_edit_snapshot") != snapshot
        for field, prefix in (("display_name", "name"), ("category", "category"), ("description", "description")):
            key = f"fm_edit_{prefix}_{selected_id}"
            if changed or key not in st.session_state:
                st.session_state[key] = record[field]
        st.session_state["fm_edit_snapshot"] = snapshot
        with st.form(f"fm_edit_{selected_id}", border=False):
            inputs = st.columns(2, gap="medium")
            with inputs[0]:
                edited_name = st.text_input("展示名称", key=f"fm_edit_name_{selected_id}")
            with inputs[1]:
                edited_category = st.text_input("分类", key=f"fm_edit_category_{selected_id}")
            edited_description = st.text_area("备注", height=80, key=f"fm_edit_description_{selected_id}")
            save = st.form_submit_button("保存信息", icon=":material/save:", type="primary")
        if save:
            try:
                service.update_file(
                    selected_id, display_name=edited_name, category=edited_category,
                    description=edited_description,
                )
                st.session_state.pop("fm_edit_snapshot", None)
                _notice("文件信息已更新。")
            except FileServiceError as exc:
                st.error(str(exc))
        st.caption("删除会同时移除原始文件和记录，请核对所选文件。")
        if st.button("删除文件", key=f"fm_delete_{selected_id}", icon=":material/delete:"):
            st.session_state["fm_pending_delete"] = selected_id
        if st.session_state["fm_pending_delete"] == selected_id:
            st.warning(f"确认删除“{record['display_name']}”（ID {selected_id}）？原始文件及记录都将删除。")
            with st.container(horizontal=True):
                if st.button("确认删除", key=f"fm_confirm_{selected_id}", icon=":material/delete_forever:"):
                    try:
                        result = service.delete_file(selected_id)
                        st.session_state["fm_pending_delete"] = None
                        _notice(result)
                    except FileServiceError as exc:
                        st.error(str(exc))
                if st.button("取消删除", key=f"fm_cancel_{selected_id}"):
                    st.session_state["fm_pending_delete"] = None
                    st.rerun()

