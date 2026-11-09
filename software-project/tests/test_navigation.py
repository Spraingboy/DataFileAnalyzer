"""通过 Streamlit AppTest 实际运行六页导航，数据保存在临时目录。"""

import config
from ui.components import PAGE_ICONS
from core import database
from streamlit.testing.v1 import AppTest


def test_all_six_pages(tmp_path, monkeypatch):
    db_path = tmp_path / "metadata.db"
    real_init = database.init_database
    monkeypatch.setattr(database, "init_database", lambda: real_init(db_path))
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    app = AppTest.from_file(str(config.BASE_DIR / "app.py"), default_timeout=20)
    app.run()
    expected_pages = [
        "系统概览", "文件管理", "数据预览", "统计分析", "数据可视化", "数据导出",
    ]
    assert not app.exception
    assert db_path.is_file()
    assert (tmp_path / "uploads").is_dir()
    assert app.sidebar.radio[0].options == [f":material/{PAGE_ICONS[key]}: {title}" for key, title in config.PAGE_TITLES.items()]
    assert list(config.PAGE_TITLES.values()) == expected_pages
    for title in expected_pages:
        app.sidebar.radio[0].set_value(title).run()
        assert not app.exception
        assert app.main.title[0].value == title
        assert app.main.info


def test_initialization_failure_shows_message(tmp_path, monkeypatch):
    def fail():
        raise PermissionError("测试目录不可写")

    monkeypatch.setattr(config, "ensure_data_directories", fail)
    app = AppTest.from_file(str(config.BASE_DIR / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert "初始化失败" in app.error[0].value
    assert not app.sidebar.radio
