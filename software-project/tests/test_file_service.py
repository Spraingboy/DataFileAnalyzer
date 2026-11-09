"""验证磁盘与数据库一致性、补偿和路径安全。"""

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID

import pytest

from core import database, file_service
from core.file_service import FileService, FileServiceError
from tests.test_data_reader import make_excel


@pytest.fixture
def service(tmp_path):
    return FileService(tmp_path / "uploads", tmp_path / "metadata.db")


@pytest.mark.parametrize("name,content", [
    ("测试.CSV", "a,b\n甲,1\n".encode("gb18030")),
    ("测试.tsv", b"a\tb\n1\t2\n"),
    ("测试.xlsx", make_excel([["a", "b"], [1, 2]])),
])
def test_import_all_types(service, name, content):
    file_id = service.import_file(name, content, display_name="展示", category="业务", description="备注")
    record = database.get_file(file_id, db_path=service.db_path)
    assert record["original_name"] == name
    assert record["display_name"] == "展示"
    assert record["category"] == "业务"
    assert record["description"] == "备注"
    assert record["created_at"].endswith("Z")
    assert record["file_size"] == len(content)
    assert (record["row_count"], record["column_count"]) == (1, 2)
    assert UUID(Path(record["stored_name"]).stem).version == 4
    assert (service.upload_dir / record["stored_name"]).read_bytes() == content


def test_user_path_never_becomes_storage_path(service):
    first = service.import_file("../../恶意.csv", b"a\n1")
    second = service.import_file("../../恶意.csv", b"a\n2")
    records = service.list_files()
    assert len(records) == 2
    assert first != second
    assert len({record["stored_name"] for record in records}) == 2
    assert len(list(service.upload_dir.iterdir())) == 2
    assert not (service.upload_dir.parent / "恶意.csv").exists()


def test_search_type_category_and_edit(service):
    first = service.import_file("a.csv", b"a\n1", category="财务")
    service.import_file("a.tsv", b"a\n2", category="财务")
    service.import_file("b.csv", b"a\n3", category="销售")
    assert [r["id"] for r in service.list_files("a", "财务", "csv")] == [first]
    old = database.get_file(first, db_path=service.db_path)
    service.update_file(first, display_name="新名称", category="", description="新备注")
    record = database.get_file(first, db_path=service.db_path)
    assert record["category"] == "未分类"
    assert record["description"] == "新备注"
    assert record["stored_name"] == old["stored_name"]
    assert record["created_at"] == old["created_at"]
    assert [r["id"] for r in service.list_files("新名称")] == [first]
    with pytest.raises(FileServiceError, match="不能为空"):
        service.update_file(first, display_name=" ", category="", description="")
    with pytest.raises(FileServiceError, match="不存在"):
        service.update_file(999, display_name="x", category="", description="")


@pytest.mark.parametrize("name,content", [("bad.csv", b""), ("bad.exe", b"a\n1"), ("bad.xlsx", b"bad")])
def test_rejected_import_creates_nothing(service, name, content):
    with pytest.raises(FileServiceError):
        service.import_file(name, content)
    assert not service.upload_dir.exists()
    assert service.list_files() == []


def test_database_insert_failure_cleans_file(service, monkeypatch):
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("database locked")
    monkeypatch.setattr(database, "insert_file", fail)
    with pytest.raises(FileServiceError, match="数据库写入失败"):
        service.import_file("data.csv", b"a\n1")
    assert list(service.upload_dir.iterdir()) == []
    assert service.list_files() == []


def test_sqlite_insert_trigger_failure_cleans_file(service):
    database.init_database(service.db_path)
    with closing(sqlite3.connect(service.db_path)) as connection, connection:
        connection.execute("""CREATE TRIGGER fail_insert BEFORE INSERT ON data_files
        BEGIN SELECT RAISE(ABORT, 'blocked'); END""")
    with pytest.raises(FileServiceError, match="数据库写入失败"):
        service.import_file("data.csv", b"a\n1")
    assert list(service.upload_dir.iterdir()) == []
    assert service.list_files() == []


def test_partial_write_failure_cleans_file(service, monkeypatch):
    original_open = Path.open
    class PartialWriter:
        def __init__(self, path):
            self.handle = original_open(path, "xb")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.handle.close()
        def write(self, content):
            self.handle.write(content[:2])
            raise OSError("disk full")
    def open_file(path, mode="r", *args, **kwargs):
        if mode == "xb":
            return PartialWriter(path)
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(FileServiceError, match="文件保存"):
        service.import_file("data.csv", b"a\n1")
    assert list(service.upload_dir.iterdir()) == []
    assert service.list_files() == []


def test_storage_collision_never_removes_existing_file(service, monkeypatch):
    fixed = file_service.uuid4()
    monkeypatch.setattr(file_service, "uuid4", lambda: fixed)
    file_id = service.import_file("a.csv", b"a\n1")
    with pytest.raises(FileServiceError):
        service.import_file("b.csv", b"a\n2")
    path = service.upload_dir / f"{fixed.hex}.csv"
    assert path.read_bytes() == b"a\n1"
    assert len(service.list_files()) == 1
    assert database.get_file(file_id, db_path=service.db_path)


def test_cleanup_failure_is_reported(service, monkeypatch):
    def fail(*args, **kwargs):
        raise PermissionError("denied")
    monkeypatch.setattr(database, "insert_file", fail)
    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(FileServiceError, match="残留文件清理失败"):
        service.import_file("data.csv", b"a\n1")
    assert len(list(service.upload_dir.iterdir())) == 1
    assert service.list_files() == []


def test_delete_success_and_missing_file(service):
    file_id = service.import_file("a.csv", b"a\n1")
    assert "已删除" in service.delete_file(file_id)
    assert service.list_files() == []
    assert list(service.upload_dir.iterdir()) == []
    file_id = service.import_file("b.csv", b"a\n2")
    record = database.get_file(file_id, db_path=service.db_path)
    (service.upload_dir / record["stored_name"]).unlink()
    assert "已缺失" in service.delete_file(file_id)
    assert service.list_files() == []
    with pytest.raises(FileServiceError, match="不存在"):
        service.delete_file(file_id)


def test_disk_delete_failure_keeps_record(service, monkeypatch):
    file_id = service.import_file("a.csv", b"a\n1")
    def fail(*args, **kwargs):
        raise PermissionError("denied")
    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(FileServiceError, match="记录已保留"):
        service.delete_file(file_id)
    assert database.get_file(file_id, db_path=service.db_path)
    assert len(list(service.upload_dir.iterdir())) == 1


def test_database_delete_failure_restores_original(service):
    file_id = service.import_file("a.csv", b"a\n1")
    with closing(sqlite3.connect(service.db_path)) as connection, connection:
        connection.execute("""CREATE TRIGGER fail_delete BEFORE DELETE ON data_files
        BEGIN SELECT RAISE(ABORT, 'blocked'); END""")
    with pytest.raises(FileServiceError, match="已保留或恢复"):
        service.delete_file(file_id)
    record = database.get_file(file_id, db_path=service.db_path)
    assert (service.upload_dir / record["stored_name"]).read_bytes() == b"a\n1"


def test_database_path_traversal_is_rejected(service):
    outside = service.upload_dir.parent / "outside.csv"
    outside.write_bytes(b"keep")
    file_id = database.insert_file("outside.csv", "../outside.csv", "csv", 4, db_path=service.db_path)
    with pytest.raises(FileServiceError, match="存储名称无效"):
        service.delete_file(file_id)
    assert outside.read_bytes() == b"keep"
    assert database.get_file(file_id, db_path=service.db_path)


def test_unwritable_upload_directory_creates_no_record(service):
    service.upload_dir.write_bytes(b"this is a file, not a directory")
    with pytest.raises(FileServiceError, match="文件保存"):
        service.import_file("a.csv", b"a\n1")
    assert service.upload_dir.read_bytes() == b"this is a file, not a directory"
    assert service.list_files() == []


def test_database_update_error_is_reported(service, monkeypatch):
    file_id = service.import_file("a.csv", b"a\n1")
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr(database, "update_file", fail)
    with pytest.raises(FileServiceError, match="信息保存失败"):
        service.update_file(file_id, display_name="b", category="", description="")
    assert service.list_files()[0]["display_name"] == "a.csv"


def test_delete_restore_failure_is_reported(service, monkeypatch):
    file_id = service.import_file("a.csv", b"a\n1")
    original_open = Path.open
    def fail_delete(*args, **kwargs):
        raise sqlite3.OperationalError("locked")
    def open_file(path, mode="r", *args, **kwargs):
        if mode == "xb":
            raise PermissionError("restore denied")
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(database, "delete_file_record", fail_delete)
    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(FileServiceError, match="文件恢复也失败"):
        service.delete_file(file_id)
    assert database.get_file(file_id, db_path=service.db_path)
