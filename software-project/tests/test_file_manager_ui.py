"""通过真实上传控件与临时目录验证完整管理交互。"""

import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

import config
from core import database
from core.file_service import FileService


@pytest.fixture
def manager(tmp_path, monkeypatch):
    db_path = tmp_path / "metadata.db"
    real_init = database.init_database
    monkeypatch.setattr(database, "init_database", lambda: real_init(db_path))
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    app = AppTest.from_file(str(config.BASE_DIR / "app.py"), default_timeout=20).run()
    app.sidebar.radio[0].set_value("文件管理").run()
    assert not app.exception
    return app, FileService()


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def upload(app, name="data.csv", content=b"a,b\n1,2\n", category="财务"):
    version = app.session_state["fm_upload_version"]
    app.file_uploader[0].set_value((name, content, "application/octet-stream"))
    app.text_input(key=f"fm_category_{version}").set_value(category)
    click(app, "导入文件")


def test_upload_and_rerun_do_not_duplicate(manager):
    app, service = manager
    assert not app.file_uploader[0].accept_multiple_files
    upload(app)
    assert app.success[0].value == "文件导入成功。"
    records = service.list_files()
    assert len(records) == 1
    assert app.file_uploader[0].value is None
    assert (service.upload_dir / records[0]["stored_name"]).read_bytes() == b"a,b\n1,2\n"
    app.run()
    assert len(service.list_files()) == 1
    assert app.dataframe[0].value.iloc[0]["原始名称"] == "data.csv"


def test_invalid_upload_and_missing_selection(manager):
    app, service = manager
    click(app, "导入文件")
    assert "选择" in app.error[0].value
    upload(app, content=b"a,b\n1,2,3")
    assert "字段数量" in app.error[0].value
    assert service.list_files() == []
    assert list(service.upload_dir.iterdir()) == []


def test_edit_and_combined_filters(manager):
    app, service = manager
    upload(app)
    first = service.list_files()[0]["id"]
    app.text_input(key=f"fm_edit_name_{first}").set_value("季度报表")
    app.text_input(key=f"fm_edit_category_{first}").set_value("销售")
    app.text_area(key=f"fm_edit_description_{first}").set_value("已核对")
    click(app, "保存信息")
    assert service.list_files()[0]["description"] == "已核对"
    upload(app, "other.tsv", b"a\tb\n1\t2\n", "财务")
    app.text_input(key="fm_search").set_value("季度").run()
    app.selectbox(key="fm_type_filter").set_value("csv").run()
    app.selectbox(key="fm_category_filter").set_value("销售").run()
    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[0].value.iloc[0]["展示名称"] == "季度报表"
    app.selectbox(key="fm_type_filter").set_value("tsv").run()
    assert "暂无符合条件" in app.info[0].value
    assert not app.exception


def test_delete_requires_second_click_and_can_cancel(manager):
    app, service = manager
    upload(app)
    record = service.list_files()[0]
    path = service.upload_dir / record["stored_name"]
    click(app, "删除文件")
    assert app.warning
    assert path.is_file()
    assert len(service.list_files()) == 1
    click(app, "取消删除")
    assert not app.warning
    assert path.is_file()
    click(app, "删除文件")
    click(app, "确认删除")
    assert not path.exists()
    assert service.list_files() == []
    assert app.success


def test_changing_selection_clears_delete_confirmation(manager):
    app, service = manager
    upload(app)
    first = service.list_files()[0]["id"]
    upload(app, "second.csv")
    second = service.list_files()[0]["id"]
    app.selectbox(key="fm_selected").set_value(first).run()
    click(app, "删除文件")
    app.selectbox(key="fm_selected").set_value(second).run()
    assert not app.warning
    assert len(service.list_files()) == 2
    assert not app.exception


def test_insert_error_is_shown_without_orphan_file(manager, monkeypatch):
    app, service = manager
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr(database, "insert_file", fail)
    upload(app)
    assert "数据库写入失败" in app.error[0].value
    assert service.list_files() == []
    assert list(service.upload_dir.iterdir()) == []


def test_leaving_page_cancels_pending_delete(manager):
    app, service = manager
    upload(app)
    click(app, "删除文件")
    app.sidebar.radio[0].set_value("系统概览").run()
    app.sidebar.radio[0].set_value("文件管理").run()
    assert not app.exception
    assert not app.warning
    assert len(service.list_files()) == 1


def test_edit_form_matches_normalized_saved_metadata_after_rerun(manager):
    app, service = manager
    upload(app)
    file_id = service.list_files()[0]["id"]
    app.text_input(key=f"fm_edit_name_{file_id}").set_value("  新名称  ")
    app.text_input(key=f"fm_edit_category_{file_id}").set_value(" ")
    click(app, "保存信息")
    assert app.text_input(key=f"fm_edit_name_{file_id}").value == "新名称"
    assert app.text_input(key=f"fm_edit_category_{file_id}").value == "未分类"
