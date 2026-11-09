"""验证读取磁盘中的实际文件及路径异常。"""

import pytest

from core import database
from core.data_reader import read_data
from core.dataset_service import DatasetLoadError, load_uploaded_file
from core.file_service import FileService
from core.analysis_service import analyze_dataframe
from tests.test_data_reader import make_excel


@pytest.fixture
def service(tmp_path):
    return FileService(tmp_path / "uploads", tmp_path / "metadata.db")


def test_reads_actual_saved_bytes(service):
    file_id = service.import_file("a.csv", b"x,y\n1,A\n2,B")
    record, content = load_uploaded_file(file_id, db_path=service.db_path, upload_dir=service.upload_dir)
    assert content == b"x,y\n1,A\n2,B"
    assert read_data(content, record["file_type"]).frame.shape == (2, 2)


def test_missing_record_and_missing_file(service):
    with pytest.raises(DatasetLoadError, match="记录不存在"):
        load_uploaded_file(1, db_path=service.db_path, upload_dir=service.upload_dir)
    file_id = service.import_file("a.csv", b"x\n1")
    record = database.get_file(file_id, db_path=service.db_path)
    (service.upload_dir / record["stored_name"]).unlink()
    with pytest.raises(DatasetLoadError, match="原始文件不存在"):
        load_uploaded_file(file_id, db_path=service.db_path, upload_dir=service.upload_dir)


def test_invalid_storage_path_never_reads_external_file(service, tmp_path):
    outside = tmp_path / "outside.csv"
    outside.write_bytes(b"x\nprivate")
    file_id = database.insert_file("outside.csv", "../outside.csv", "csv", 9, db_path=service.db_path)
    with pytest.raises(DatasetLoadError, match="存储名称无效"):
        load_uploaded_file(file_id, db_path=service.db_path, upload_dir=service.upload_dir)


@pytest.mark.parametrize("name,content", [
    ("known.csv", "数值,类别\n1,A\n2,B\n3,B\n3,B".encode("gb18030")),
    ("known.tsv", "数值\t类别\n1\tA\n2\tB\n3\tB\n3\tB".encode("utf-8-sig")),
    ("known.xlsx", make_excel([["数值", "类别"], [1, "A"], [2, "B"], [3, "B"], [3, "B"]], [["忽略此表"], [999]])),
])
def test_statistics_from_each_uploaded_format(service, name, content):
    file_id = service.import_file(name, content)
    record, actual = load_uploaded_file(file_id, db_path=service.db_path, upload_dir=service.upload_dir)
    report = analyze_dataframe(read_data(actual, record["file_type"]).frame)
    row = report["numeric"].iloc[0]
    assert row["field"] == "数值"
    assert row["mean"] == 2.25
    assert row["std"] == pytest.approx((11 / 12) ** 0.5)
    assert report["overview"]["duplicate_row_count"] == 1
