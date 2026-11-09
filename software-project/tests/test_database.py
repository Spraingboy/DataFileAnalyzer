"""使用临时数据库验证接口，不修改真实元数据。"""

import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from core.database import (
    delete_file_record,
    get_dashboard_stats,
    get_file,
    init_database,
    insert_file,
    list_files,
    update_file,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "nested" / "metadata.db"


def add_file(db_path, **changes):
    metadata = {
        "original_name": "测试数据.csv",
        "stored_name": f"{uuid4()}.csv",
        "file_type": "csv",
        "file_size": 128,
        "row_count": 3,
        "column_count": 2,
    }
    metadata.update(changes)
    return insert_file(**metadata, db_path=db_path)


def test_empty_database_and_repeated_initialization(db_path):
    init_database(db_path)
    init_database(db_path)
    assert db_path.is_file()
    assert list_files(db_path=db_path) == []
    assert get_file(1, db_path=db_path) is None
    assert get_dashboard_stats(db_path=db_path) == {
        "total_files": 0,
        "total_size": 0,
        "total_rows": 0,
        "category_count": 0,
        "file_type_counts": {"csv": 0, "tsv": 0, "xlsx": 0},
    }


def test_metadata_lifecycle_and_persistence(db_path):
    file_id = add_file(db_path)
    init_database(db_path)
    record = get_file(file_id, db_path=db_path)
    assert record["original_name"] == "测试数据.csv"
    assert record["display_name"] == "测试数据.csv"
    assert record["created_at"].endswith("Z")
    assert record["updated_at"].endswith("Z")
    assert update_file(
        file_id, display_name="销售统计", category="销售", description="说明",
        db_path=db_path,
    )
    assert get_file(file_id, db_path=db_path)["description"] == "说明"
    assert update_file(file_id, description="", db_path=db_path)
    record = get_file(file_id, db_path=db_path)
    assert record["description"] == ""
    assert record["display_name"] == "销售统计"
    assert record["category"] == "销售"
    assert record["stored_name"].endswith(".csv")
    assert update_file(file_id, db_path=db_path)
    assert delete_file_record(file_id, db_path=db_path)
    assert get_file(file_id, db_path=db_path) is None
    assert not delete_file_record(file_id, db_path=db_path)
    assert not update_file(file_id, category="销售", db_path=db_path)


def test_search_filter_and_parameterized_queries(db_path):
    first = add_file(db_path, original_name="100%_统计.csv", category="财务")
    second = add_file(db_path, original_name="SALES.csv", category="销售")
    assert [r["id"] for r in list_files(db_path=db_path)] == [second, first]
    assert [r["id"] for r in list_files("%_", db_path=db_path)] == [first]
    assert [r["id"] for r in list_files("sales", "销售", db_path=db_path)] == [second]
    assert list_files("sales", "财务", db_path=db_path) == []
    assert list_files("' OR 1=1 --", db_path=db_path) == []
    assert list_files(category="' OR 1=1 --", db_path=db_path) == []
    assert update_file(first, display_name="'报价'", db_path=db_path)
    assert [r["id"] for r in list_files("'报价'", db_path=db_path)] == [first]
    assert len(list_files(db_path=db_path)) == 2


def test_dashboard_aggregates_metadata(db_path):
    add_file(db_path, category="甲")
    add_file(db_path, category="甲", file_type=".XLSX", file_size=72, row_count=7)
    add_file(db_path, category="乙", file_type="tsv", file_size=0, row_count=0)
    assert get_dashboard_stats(db_path=db_path) == {
        "total_files": 3,
        "total_size": 200,
        "total_rows": 10,
        "category_count": 2,
        "file_type_counts": {"csv": 1, "tsv": 1, "xlsx": 1},
    }


@pytest.mark.parametrize("changes", [
    {"file_size": -1}, {"row_count": -1}, {"column_count": -1},
    {"file_type": "exe"}, {"original_name": " "}, {"category": ""},
])
def test_invalid_metadata_rolls_back(db_path, changes):
    with pytest.raises(sqlite3.IntegrityError):
        add_file(db_path, **changes)
    assert list_files(db_path=db_path) == []


def test_duplicate_storage_name_and_failed_update(db_path):
    stored_name = f"{uuid4()}.csv"
    file_id = add_file(db_path, stored_name=stored_name)
    with pytest.raises(sqlite3.IntegrityError):
        add_file(db_path, stored_name=stored_name)
    with pytest.raises(sqlite3.IntegrityError):
        update_file(file_id, display_name="", db_path=db_path)
    assert get_file(file_id, db_path=db_path)["display_name"] == "测试数据.csv"
    assert len(list_files(db_path=db_path)) == 1


def test_delete_record_does_not_delete_file(tmp_path, db_path):
    # 实际字节只用于验证职责边界，不作为界面展示数据。
    stored_name = f"{uuid4()}.csv"
    actual_file = tmp_path / stored_name
    actual_file.write_text("a\n1\n", encoding="utf-8")
    file_id = add_file(db_path, stored_name=stored_name)
    assert delete_file_record(file_id, db_path=db_path)
    assert actual_file.is_file()


def test_failed_delete_keeps_record(db_path):
    file_id = add_file(db_path)
    # 用触发器稳定模拟删除失败，避免依赖不同系统的文件权限行为。
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            """CREATE TRIGGER prevent_delete BEFORE DELETE ON data_files
            BEGIN SELECT RAISE(ABORT, 'delete blocked'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError, match="delete blocked"):
        delete_file_record(file_id, db_path=db_path)
    assert get_file(file_id, db_path=db_path) is not None


def test_edit_preserves_import_metadata_and_upload_time(db_path):
    file_id = add_file(db_path, encoding="gb18030")
    before = get_file(file_id, db_path=db_path)
    assert update_file(file_id, display_name="新名称", category="业务", db_path=db_path)
    after = get_file(file_id, db_path=db_path)
    for field in (
        "original_name", "stored_name", "file_type", "file_size", "row_count",
        "column_count", "encoding", "created_at",
    ):
        assert after[field] == before[field]
