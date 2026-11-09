"""从真实上传文件读取数据，测试预览与统计交互和缓存失效。"""

import math

import pytest
from streamlit.testing.v1 import AppTest

import config
from core import database
from core.file_service import FileService
from ui.analysis_page import _cached_frame, _cached_report


@pytest.fixture
def analyzer(tmp_path, monkeypatch):
    db_path = tmp_path / "metadata.db"
    real_init = database.init_database
    monkeypatch.setattr(database, "init_database", lambda: real_init(db_path))
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    _cached_frame.clear()
    _cached_report.clear()
    app = AppTest.from_file(str(config.BASE_DIR / "app.py"), default_timeout=20).run()
    return app, FileService()


def open_page(app, page):
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception


def test_preview_limits_fields_and_actual_shape(analyzer):
    app, service = analyzer
    content = "amount,group\n" + "".join(f"{index},group_{index % 2}\n" for index in range(120))
    file_id = service.import_file("rows.csv", content.encode("utf-8"))
    open_page(app, "数据预览")
    assert any("120 行、2 列" in caption.value for caption in app.caption)
    fields = app.container(key="card_preview_fields").dataframe[0].value
    assert fields["字段"].tolist() == ["amount", "group"]
    assert fields["数值字段"].tolist() == [True, False]
    assert len(app.container(key="card_preview_table").dataframe[0].value) == 20
    for limit in [50, 100]:
        app.segmented_control(key="preview_limit").set_value(limit).run()
        assert len(app.container(key="card_preview_table").dataframe[0].value) == limit
    app.multiselect(key=f"preview_columns_{file_id}").set_value(["group"]).run()
    assert list(app.container(key="card_preview_table").dataframe[0].value.columns) == ["group"]
    app.multiselect(key=f"preview_columns_{file_id}").set_value([]).run()
    assert "至少选择" in app.info[0].value
    assert len(app.dataframe) == 1
    assert not app.exception


def test_statistics_match_actual_uploaded_data(analyzer):
    app, service = analyzer
    content = b"amount,group,empty\n1,A,\n2,A,\n3,B,\n4,B,\n,,\n4,B,\n"
    service.import_file("known.csv", content)
    open_page(app, "统计分析")
    overview = app.dataframe[0].value.set_index("指标")
    assert overview.loc["数据行数", "值"] == "6"
    assert overview.loc["重复行数", "值"] == "1"
    row = app.dataframe[1].value.iloc[0]
    assert row["有效值数量"] == 5
    assert row["均值"] == pytest.approx(2.8)
    assert row["标准差"] == pytest.approx(math.sqrt(1.7))
    missing = app.dataframe[2].value.set_index("字段")
    assert missing.loc["amount", "缺失率"] == "16.67%"
    assert missing.loc["empty", "缺失率"] == "100.00%"
    assert app.dataframe[3].value.to_dict("records") == [
        {"分类值": "B", "频次": 3}, {"分类值": "A", "频次": 2},
    ]


def test_no_numeric_and_all_empty_category(analyzer):
    app, service = analyzer
    file_id = service.import_file("text.csv", b"label,empty\nA,\nB,\n")
    open_page(app, "统计分析")
    assert any("没有可统计的数值" in notice.value for notice in app.info)
    app.selectbox(key=f"analysis_category_{file_id}").set_value("empty").run()
    assert any("全部为空" in notice.value for notice in app.info)
    assert not app.exception


def test_missing_file_is_detected_even_when_cached(analyzer):
    app, service = analyzer
    file_id = service.import_file("missing.csv", b"x\n1\n2")
    open_page(app, "数据预览")
    record = database.get_file(file_id, db_path=service.db_path)
    (service.upload_dir / record["stored_name"]).unlink()
    app.run()
    assert "原始文件不存在" in app.error[0].value
    assert not app.dataframe
    assert not app.exception


def test_changed_bytes_recompute_statistics_and_corruption_is_reported(analyzer):
    app, service = analyzer
    file_id = service.import_file("changed.csv", b"x\n1\n2")
    record = database.get_file(file_id, db_path=service.db_path)
    path = service.upload_dir / record["stored_name"]
    open_page(app, "统计分析")
    assert app.dataframe[1].value.iloc[0]["均值"] == 1.5
    path.write_bytes(b"x\n4\n5")  # 字节长度不变，内容变化仍应使缓存失效。
    app.run()
    assert app.dataframe[1].value.iloc[0]["均值"] == 4.5
    path.write_bytes(b'x\n"broken')
    app.run()
    assert "格式损坏" in app.error[0].value
    assert not app.dataframe
    assert not app.exception


def test_switching_files_uses_corresponding_fields(analyzer):
    app, service = analyzer
    first = service.import_file("first.csv", b"a\n1")
    second = service.import_file("second.tsv", b"b\tc\n2\ttext")
    open_page(app, "数据预览")
    assert list(app.container(key="card_preview_table").dataframe[0].value.columns) == ["b", "c"]
    app.selectbox(key="preview_file").set_value(first).run()
    assert list(app.container(key="card_preview_table").dataframe[0].value.columns) == ["a"]
    app.selectbox(key="preview_file").set_value(second).run()
    assert list(app.container(key="card_preview_table").dataframe[0].value.columns) == ["b", "c"]
    assert not app.exception


def test_preview_clears_selected_fields_after_schema_changes(analyzer):
    app, service = analyzer
    file_id = service.import_file("schema.csv", b"old\n1")
    page_name = "数据预览"
    open_page(app, page_name)
    record = database.get_file(file_id, db_path=service.db_path)
    (service.upload_dir / record["stored_name"]).write_bytes(b"new\n2")
    app.run()
    assert not app.exception
    assert not app.error
    assert app.multiselect(key=f"preview_columns_{file_id}").options == ["new"]
    assert app.multiselect(key=f"preview_columns_{file_id}").value == []
    assert "至少选择" in app.info[0].value
