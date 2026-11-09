"""用 AppTest 和实际字节回读验证图表与下载按钮的数据一致性。"""

from io import BytesIO

import pandas as pd
import pytest
import streamlit as st
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

import config
from core import database
from core.chart_service import CHART_TYPES
from core.export_service import ExportError
from core.file_service import FileService
from ui import charts, export as export_page
from ui.analysis_page import _cached_frame, _cached_report


@pytest.fixture
def application(tmp_path, monkeypatch):
    db_path = tmp_path / "metadata.db"
    real_init = database.init_database
    monkeypatch.setattr(database, "init_database", lambda: real_init(db_path))
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    for cached in (_cached_frame, _cached_report, charts._cached_chart, export_page._raw_frame, export_page._export_bytes):
        cached.clear()
    downloads = {}
    figures = []
    original_download = st.download_button
    original_plot = st.plotly_chart
    def download(label, data, *args, **kwargs):
        downloads[label] = {"data": data, "file_name": kwargs.get("file_name"), "mime": kwargs.get("mime")}
        return original_download(label, data, *args, **kwargs)
    def plot(figure, *args, **kwargs):
        figures.append(figure)
        return original_plot(figure, *args, **kwargs)
    monkeypatch.setattr(st, "download_button", download)
    monkeypatch.setattr(st, "plotly_chart", plot)
    app = AppTest.from_file(str(config.BASE_DIR / "app.py"), default_timeout=20).run()
    return app, FileService(), downloads, figures


def page(app, title):
    app.sidebar.radio[0].set_value(title).run()
    assert not app.exception


def generate(app):
    app.button(key="export_generate").click().run()
    assert not app.exception


def test_all_four_charts_and_field_restrictions(application):
    app, service, _, figures = application
    file_id = service.import_file("charts.csv", b"x,y,group,empty\n1,3,A,\n2,4,B,\n3,5,A,\n")
    page(app, "数据可视化")
    assert app.selectbox(key=f"chart_x_{file_id}_{CHART_TYPES[0]}").options == ["group"]
    assert figures[-1].data[0].type == "bar"
    for kind in CHART_TYPES[1:]:
        app.selectbox(key="chart_type").set_value(kind).run()
        assert not app.exception
        assert app.selectbox(key=f"chart_x_{file_id}_{kind}").options == ["x", "y"]
        assert app.get("plotly_chart")
    assert app.selectbox(key=f"chart_y_{file_id}_x").options == ["y"]
    assert list(figures[-1].data[0].x) == [1, 2, 3]
    assert list(figures[-1].data[0].y) == [3, 4, 5]


def test_chart_sampling_does_not_change_statistics_or_export(application):
    app, service, downloads, figures = application
    service.import_file("large.csv", ("x,y\n" + "".join(f"{n},{n * 2}\n" for n in range(3001))).encode())
    page(app, "数据可视化")
    app.selectbox(key="chart_type").set_value(CHART_TYPES[1]).run()
    assert len(figures[-1].data[0].x) == 2000
    assert any("等间隔抽样" in caption.value for caption in app.caption)
    page(app, "统计分析")
    assert app.dataframe[1].value.iloc[0]["有效值数量"] == 3001
    assert app.dataframe[1].value.iloc[0]["均值"] == 1500
    page(app, "数据导出")
    generate(app)
    exported = pd.read_csv(BytesIO(downloads["下载生成文件"]["data"]))
    assert exported.shape == (3001, 2)
    assert exported.iloc[-1]["x"] == 3000


def test_original_and_selected_exports_match_current_file_and_order(application):
    app, service, downloads, _ = application
    original = "编号,姓名,数值\n001,张三,1\n002,李四,2\n".encode("gb18030")
    file_id = service.import_file("原始.csv", original)
    page(app, "数据导出")
    assert downloads["下载原始文件"]["data"] == original
    app.multiselect(key=f"export_columns_{file_id}").set_value(["姓名", "编号"]).run()
    generate(app)
    payload = downloads["下载生成文件"]["data"]
    result = pd.read_csv(BytesIO(payload), dtype=str)
    assert list(result.columns) == ["姓名", "编号"]
    assert result["编号"].tolist() == ["001", "002"]
    app.selectbox(key="export_kind").set_value(export_page.EXPORT_TYPES[1]).run()
    assert [button.label for button in app.download_button] == ["下载原始文件"]
    generate(app)
    workbook = load_workbook(BytesIO(downloads["下载生成文件"]["data"]), read_only=True)
    assert list(workbook.active.values) == [("姓名", "编号"), ("张三", "001"), ("李四", "002")]
    workbook.close()


def test_statistics_downloads_respect_selection(application):
    app, service, downloads, _ = application
    file_id = service.import_file("stats.csv", b"x,y,label\n1,10,A\n2,20,B\n,30,B")
    page(app, "数据导出")
    app.multiselect(key=f"export_columns_{file_id}").set_value(["label", "x"]).run()
    app.selectbox(key="export_kind").set_value(export_page.EXPORT_TYPES[2]).run()
    generate(app)
    numeric = pd.read_csv(BytesIO(downloads["下载生成文件"]["data"]))
    assert numeric["字段"].tolist() == ["x"]
    assert numeric.iloc[0]["均值"] == 1.5
    app.selectbox(key="export_kind").set_value(export_page.EXPORT_TYPES[3]).run()
    generate(app)
    missing = pd.read_csv(BytesIO(downloads["下载生成文件"]["data"]))
    assert missing["字段"].tolist() == ["label", "x"]
    assert missing.iloc[1]["缺失率"] == pytest.approx(1 / 3)


def test_empty_selection_and_export_failure_show_messages(application, monkeypatch):
    app, service, _, _ = application
    file_id = service.import_file("a.csv", b"x\n1")
    page(app, "数据导出")
    app.multiselect(key=f"export_columns_{file_id}").set_value([]).run()
    assert "至少选择" in app.info[0].value
    assert not app.button
    app.multiselect(key=f"export_columns_{file_id}").set_value(["x"]).run()
    def fail(*args, **kwargs):
        raise ExportError("模拟导出失败")
    monkeypatch.setattr(export_page, "export_selected_csv", fail)
    generate(app)
    assert "导出失败" in app.error[0].value
    assert [button.label for button in app.download_button] == ["下载原始文件"]


def test_changing_file_or_content_invalidates_prepared_download(application):
    app, service, downloads, _ = application
    first = service.import_file("first.csv", b"x\n1")
    second = service.import_file("second.csv", b"y\n2")
    page(app, "数据导出")
    generate(app)
    app.selectbox(key="export_file").set_value(first).run()
    assert [button.label for button in app.download_button] == ["下载原始文件"]
    generate(app)
    assert pd.read_csv(BytesIO(downloads["下载生成文件"]["data"])).columns.tolist() == ["x"]
    record = database.get_file(first, db_path=service.db_path)
    path = service.upload_dir / record["stored_name"]
    path.write_bytes(b"x\n9")
    app.run()
    assert [button.label for button in app.download_button] == ["下载原始文件"]
    generate(app)
    assert pd.read_csv(BytesIO(downloads["下载生成文件"]["data"])).iloc[0, 0] == 9
    app.selectbox(key="export_file").set_value(second).run()
    assert not app.exception


def test_missing_file_removes_charts_and_downloads(application):
    app, service, _, _ = application
    file_id = service.import_file("a.csv", b"x\n1")
    page(app, "数据导出")
    generate(app)
    record = database.get_file(file_id, db_path=service.db_path)
    (service.upload_dir / record["stored_name"]).unlink()
    app.run()
    assert "原始文件不存在" in app.error[0].value
    assert not app.download_button
    page(app, "数据可视化")
    assert "原始文件不存在" in app.error[0].value
    assert not app.get("plotly_chart")


def test_corrupt_file_still_allows_original_download(application):
    app, service, downloads, _ = application
    file_id = service.import_file("a.csv", b"x\n1")
    record = database.get_file(file_id, db_path=service.db_path)
    (service.upload_dir / record["stored_name"]).write_bytes(b'x\n"broken')
    page(app, "数据导出")
    assert "格式损坏" in app.error[0].value
    assert downloads["下载原始文件"]["data"] == b'x\n"broken'
    assert [button.label for button in app.download_button] == ["下载原始文件"]


def test_all_missing_values_and_no_numeric_export(application):
    app, service, downloads, _ = application
    service.import_file("empty_values.csv", b"a,b\n,\n,\n")
    page(app, "数据可视化")
    assert "没有适用" in app.info[0].value
    app.selectbox(key="chart_type").set_value(CHART_TYPES[2]).run()
    assert "没有包含有限数值" in app.info[0].value
    assert not app.get("plotly_chart")
    page(app, "数据导出")
    app.selectbox(key="export_kind").set_value(export_page.EXPORT_TYPES[2]).run()
    generate(app)
    assert "没有数值统计" in app.error[0].value
    app.selectbox(key="export_kind").set_value(export_page.EXPORT_TYPES[3]).run()
    generate(app)
    missing = pd.read_csv(BytesIO(downloads["下载生成文件"]["data"]))
    assert missing["缺失数量"].tolist() == [2, 2]
    assert missing["缺失率"].tolist() == [1, 1]


def test_changed_file_schema_clears_invalid_selected_fields(application):
    app, service, _, _ = application
    file_id = service.import_file("schema.csv", b"x\n1")
    page(app, "数据导出")
    generate(app)
    record = database.get_file(file_id, db_path=service.db_path)
    (service.upload_dir / record["stored_name"]).write_bytes(b"new\n2")
    app.run()
    assert app.multiselect(key=f"export_columns_{file_id}").options == ["new"]
    assert not app.multiselect(key=f"export_columns_{file_id}").value
    assert [button.label for button in app.download_button] == ["下载原始文件"]
    assert not app.exception
