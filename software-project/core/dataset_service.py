"""只读载入已上传文件，不修改既有文件管理接口或元数据。"""

import re
import sqlite3
from pathlib import Path
from uuid import UUID

import config
from core import database


class DatasetLoadError(ValueError):
    """记录、原始文件或存储路径异常。"""


def load_uploaded_file(file_id: int, *, db_path=None, upload_dir=None) -> tuple[dict, bytes]:
    try:
        record = database.get_file(
            file_id, db_path=config.DATABASE_PATH if db_path is None else db_path
        )
        if record is None:
            raise DatasetLoadError("文件记录不存在，请返回文件管理刷新列表。")
        name = record["stored_name"]
        if not re.fullmatch(r"[0-9a-fA-F-]{32,36}\.(csv|tsv|xlsx)", name):
            raise DatasetLoadError("存储名称无效，已停止读取文件。")
        try:
            UUID(name.rsplit(".", 1)[0])
        except ValueError as exc:
            raise DatasetLoadError("存储名称中的 UUID 无效。") from exc
        if name.rsplit(".", 1)[1] != record["file_type"]:
            raise DatasetLoadError("元数据类型与存储文件扩展名不一致。")
        root = Path(config.UPLOAD_DIR if upload_dir is None else upload_dir).resolve()
        path = root / name
        if path.is_symlink() or path.resolve().parent != root:
            raise DatasetLoadError("存储路径异常，已停止读取文件。")
        with path.open("rb") as handle:
            content = handle.read(config.MAX_FILE_SIZE_BYTES + 1)
        if len(content) > config.MAX_FILE_SIZE_BYTES:
            raise DatasetLoadError("磁盘文件超过 10MB，请返回文件管理检查。")
        return record, content
    except FileNotFoundError as exc:
        raise DatasetLoadError("原始文件不存在，可能已移动或删除，请返回文件管理检查。") from exc
    except (OSError, sqlite3.Error) as exc:
        raise DatasetLoadError("文件读取失败，请检查文件和数据库的读取权限。") from exc
