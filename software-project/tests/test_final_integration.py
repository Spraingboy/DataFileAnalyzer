"""最终整合验收：真实上传控件、六页、新会话、磁盘和 SQLite。"""

from contextlib import closing
from io import BytesIO
import json
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest
import streamlit as st
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

import config
from core import database
from core.chart_service import CHART_TYPES
from core.analysis_service import analyze_dataframe
from core.data_reader import read_data
from core.dataset_service import load_uploaded_file
from core.file_service import FileService
from tests.test_data_reader import make_excel
from ui import charts, dashboard, export as export_page
from ui.analysis_page import _cached_frame, _cached_report
from ui.components import PAGE_ICONS


@pytest.fixture
def final_app(tmp_path, monkeypatch):
    db_path = tmp_path / "metadata.db"
    real_init = database.init_database
    monkeypatch.setattr(database, "init_database", lambda: real_init(db_path))
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    for cached in (_cached_frame, _cached_report, charts._cached_chart, export_page._raw_frame, export_page._export_bytes):
        cached.clear()
    downloads, figures = {}, []
    original_download, original_plot = st.download_button, st.plotly_chart
    def download(label, data, *args, **kwargs):
        downloads[label] = data
        return original_download(label, data, *args, **kwargs)
    def plot(figure, *args, **kwargs):
        figures.append(figure)
        return original_plot(figure, *args, **kwargs)
    monkeypatch.setattr(st, "download_button", download)
    monkeypatch.setattr(st, "plotly_chart", plot)
    app = AppTest.from_file(str(config.BASE_DIR / "app.py"), default_timeout=30).run()
    return app, FileService(), downloads, figures


def page(app, title):
    app.sidebar.radio[0].set_value(title).run()
    assert not app.exception
    assert app.main.title[0].value == title


def button(app, label):
    next(item for item in app.button if item.label == label).click().run()
    assert not app.exception


INPUTS = [
    (f"验收.{kind}", (f"数值{delimiter}数量{delimiter}分类\n"
        f"1{delimiter}2{delimiter}A\n2{delimiter}4{delimiter}A\n"
        f"3{delimiter}6{delimiter}B\n3{delimiter}6{delimiter}B\n{delimiter}{delimiter}\n").encode(encoding))
    for kind, delimiter in (("csv", ","), ("tsv", "\t"))
    for encoding in ("utf-8", "utf-8-sig", "gb18030")
]
INPUTS.append(("验收.xlsx", make_excel([
    ["数值", "数量", "分类"], [1, 2, "A"], [2, 4, "A"],
    [3, 6, "B"], [3, 6, "B"], [None, None, None],
], [["不分析"], [999]])))


@pytest.mark.parametrize("name,content", INPUTS, ids=["csv-utf8", "csv-bom", "csv-gb", "tsv-utf8", "tsv-bom", "tsv-gb", "xlsx"])
def test_upload_to_all_six_pages_exports_persistence_and_delete(final_app, name, content):
    app, service, downloads, figures = final_app
    assert app.sidebar.radio[0].options == [f":material/{PAGE_ICONS[key]}: {title}" for key, title in config.PAGE_TITLES.items()]
    assert all("阶段" not in caption.value for caption in app.sidebar.caption)
    page(app, "文件管理")
    app.file_uploader[0].set_value((name, content, "application/octet-stream"))
    app.text_input(key="fm_name_0").set_value("验收数据")
    app.text_input(key="fm_category_0").set_value("验收分类")
    button(app, "导入文件")
    record = service.list_files()[0]
    file_id = record["id"]
    path = service.upload_dir / record["stored_name"]
    assert path.read_bytes() == content
    assert (record["row_count"], record["column_count"]) == (5, 3)
    app.run()
    app.run()
    assert len(service.list_files()) == 1
    assert app.file_uploader[0].value is None

    page(app, "系统概览")
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["文件数量"] == "1"
    assert metrics["数据总行数"] == "5"
    assert metrics["支持格式数量"] == "3"
    assert database.get_dashboard_stats(db_path=service.db_path)["category_count"] == 1
    assert any("当前共 1 个分类" in caption.value for caption in app.caption)
    assert app.dataframe[0].value["文件数量"].sum() == 1

    page(app, "数据预览")
    assert app.container(key="card_preview_table").dataframe[0].value.shape == (5, 3)
    page(app, "统计分析")
    overview = app.dataframe[0].value.set_index("指标")
    assert overview.loc["重复行数", "值"] == "1"
    numeric = app.dataframe[1].value.set_index("字段")
    assert numeric.loc["数值", "均值"] == 2.25
    assert numeric.loc["数值", "标准差"] == pytest.approx((11 / 12) ** 0.5)
    assert app.dataframe[2].value["缺失率"].tolist() == ["20.00%"] * 3

    page(app, "数据可视化")
    assert list(figures[-1].data[0].y) == [2, 2]
    for kind in CHART_TYPES[1:]:
        app.selectbox(key="chart_type").set_value(kind).run()
        assert not app.exception
        assert len(figures[-1].data[0].x) == 4

    page(app, "数据导出")
    assert downloads["下载原始文件"] == content
    selected = ["分类", "数量", "数值"]
    app.multiselect(key=f"export_columns_{file_id}").set_value(selected).run()
    for kind in export_page.EXPORT_TYPES:
        app.selectbox(key="export_kind").set_value(kind).run()
        button(app, "生成下载文件")
        data = downloads["下载生成文件"]
        if kind == export_page.EXPORT_TYPES[1]:
            workbook = load_workbook(BytesIO(data), read_only=True)
            assert workbook.active.max_row == 6
            assert workbook.active.max_column == 3
            assert list(next(workbook.active.values)) == selected
            workbook.close()
        else:
            table = pd.read_csv(BytesIO(data))
            if kind == export_page.EXPORT_TYPES[0]:
                assert table.shape == (5, 3)
                assert list(table.columns) == selected
            elif kind == export_page.EXPORT_TYPES[2]:
                assert table["字段"].tolist() == ["数量", "数值"]
                assert table["有效值数量"].tolist() == [4, 4]
            else:
                assert table["字段"].tolist() == selected
                assert table["缺失率"].tolist() == [0.2] * 3
    app.download_button(key="export_download").click().run()
    assert not app.exception
    assert len(service.list_files()) == 1
    assert len(list(service.upload_dir.iterdir())) == 1

    # 新会话不能依赖旧会话内存；重新初始化也不能清空 SQLite。
    fresh = AppTest.from_file(str(config.BASE_DIR / "app.py"), default_timeout=30).run()
    assert fresh.metric[0].value == "1"
    page(fresh, "文件管理")
    assert fresh.dataframe[0].value.iloc[0]["展示名称"] == "验收数据"

    page(app, "文件管理")
    button(app, "删除文件")
    button(app, "确认删除")
    assert not path.exists()
    assert service.list_files() == []
    assert list(service.upload_dir.iterdir()) == []
    page(app, "系统概览")
    assert app.metric[0].value == "0"
    for title in ("数据预览", "统计分析", "数据可视化", "数据导出"):
        page(app, title)
        assert "暂无已上传文件" in app.info[0].value
    with closing(sqlite3.connect(service.db_path)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_export_ready_is_cleared_on_page_change(final_app):
    app, service, _, _ = final_app
    service.import_file("a.csv", b"x\n1")
    page(app, "数据导出")
    button(app, "生成下载文件")
    assert len(app.download_button) == 2
    page(app, "系统概览")
    page(app, "数据导出")
    assert [item.label for item in app.download_button] == ["下载原始文件"]


@pytest.mark.parametrize("name,content", [
    ("bad.csv", b"x\n1"), ("bad.tsv", b"x\n1"),
    ("bad.xlsx", make_excel([["x"], [1]])),
])
def test_corrupted_or_missing_upload_is_handled_on_all_data_pages(final_app, name, content):
    app, service, downloads, _ = final_app
    file_id = service.import_file(name, content)
    record = database.get_file(file_id, db_path=service.db_path)
    path = service.upload_dir / record["stored_name"]
    page(app, "数据预览")  # 先形成缓存，再损坏文件。
    invalid = b"not an Excel workbook" if name.endswith("xlsx") else b'x\n"broken'
    path.write_bytes(invalid)
    for title in ("数据预览", "统计分析", "数据可视化", "数据导出"):
        page(app, title)
        assert app.error
        assert not app.get("plotly_chart")
    assert downloads["下载原始文件"] == invalid
    path.unlink()
    for title in ("数据预览", "统计分析", "数据可视化", "数据导出"):
        page(app, title)
        assert "原始文件不存在" in app.error[0].value
        assert not app.download_button
    page(app, "文件管理")
    button(app, "删除文件")
    button(app, "确认删除")
    assert service.list_files() == []


def test_metadata_persists_in_a_new_python_process(final_app):
    _, service, _, _ = final_app
    file_id = service.import_file("persist.csv", b"x\n1\n2", description="持久化")
    script = """
import json, sys
from core.database import init_database, get_dashboard_stats
from core.dataset_service import load_uploaded_file
init_database(sys.argv[1])
record, content = load_uploaded_file(int(sys.argv[3]), db_path=sys.argv[1], upload_dir=sys.argv[2])
print(json.dumps({'description': record['description'], 'content': content.decode(), 'count': get_dashboard_stats(db_path=sys.argv[1])['total_files']}))
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(service.db_path), str(service.upload_dir), str(file_id)],
        cwd=config.BASE_DIR, capture_output=True, text=True, encoding="utf-8", check=True, timeout=30,
    )
    assert json.loads(result.stdout) == {"description": "持久化", "content": "x\n1\n2", "count": 1}


def test_dashboard_database_error_is_a_user_message(final_app, monkeypatch):
    app, _, _, _ = final_app
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr(dashboard, "get_dashboard_stats", fail)
    app.run()
    assert not app.exception
    assert "概况读取失败" in app.error[0].value


def test_corrupt_sqlite_is_reported_at_startup(final_app):
    app, service, _, _ = final_app
    service.db_path.write_bytes(b"this is not SQLite")
    app.run()
    assert not app.exception
    assert "初始化失败" in app.error[0].value
    assert not app.sidebar.radio


def test_combined_row_column_limits_with_real_upload_bytes(final_app):
    _, service, _, _ = final_app
    header = ",".join(f"c{index}" for index in range(100)).encode() + b"\n"
    block = b"".join((str(value).encode() + b",") * 99 + str(value).encode() + b"\n" for value in range(10))
    content = header + block * 5000
    assert len(content) <= config.MAX_FILE_SIZE_BYTES
    file_id = service.import_file("limits.csv", content)
    record, actual = load_uploaded_file(file_id, db_path=service.db_path, upload_dir=service.upload_dir)
    assert (record["row_count"], record["column_count"]) == (50000, 100)
    report = analyze_dataframe(read_data(actual, "csv").frame)
    assert report["overview"]["row_count"] == 50000
    assert report["overview"]["duplicate_row_count"] == 49990
    assert report["numeric"]["count"].tolist() == [50000] * 100
    assert report["numeric"]["mean"].tolist() == [4.5] * 100
    assert report["missing"]["missing_count"].sum() == 0
