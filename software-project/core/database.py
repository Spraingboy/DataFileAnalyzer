"""SQLite 仅保存文件元数据，实际文件由后续文件模块保存。"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS data_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_name TEXT NOT NULL CHECK (length(trim(original_name)) > 0),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    stored_name TEXT NOT NULL UNIQUE CHECK (length(trim(stored_name)) > 0),
    file_type TEXT NOT NULL CHECK (file_type IN ('csv', 'tsv', 'xlsx')),
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    column_count INTEGER NOT NULL DEFAULT 0 CHECK (column_count >= 0),
    category TEXT NOT NULL DEFAULT '未分类' CHECK (length(trim(category)) > 0),
    description TEXT NOT NULL DEFAULT '',
    encoding TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


@contextmanager
def _connection(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """每次操作独立连接，提交或回滚后始终关闭连接。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        # IF NOT EXISTS 保证初始化可重复执行，也支持直接调用数据库接口。
        connection.execute(SCHEMA)
        with connection:
            yield connection
    finally:
        connection.close()


def init_database(db_path: str | Path = DATABASE_PATH) -> None:
    """自动创建数据库和 data_files 表，不清空已有数据。"""
    with _connection(db_path):
        pass


def insert_file(
    original_name: str,
    stored_name: str,
    file_type: str,
    file_size: int,
    row_count: int = 0,
    column_count: int = 0,
    category: str = "未分类",
    description: str = "",
    encoding: str | None = None,
    display_name: str | None = None,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> int:
    """插入元数据并返回 ID；stored_name 由文件模块提供 UUID 文件名。

    大小单位为字节，行数不包含表头。约束冲突抛出 sqlite3.IntegrityError。
    此函数不创建实际文件，也不代替后续文件读取和上传校验。
    """
    with _connection(db_path) as connection:
        cursor = connection.execute(
            """INSERT INTO data_files (
                original_name, display_name, stored_name, file_type, file_size,
                row_count, column_count, category, description, encoding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                original_name,
                original_name if display_name is None else display_name,
                stored_name,
                file_type.lower().lstrip("."),
                file_size,
                row_count,
                column_count,
                category,
                description,
                encoding,
            ),
        )
        return int(cursor.lastrowid)


def get_file(
    file_id: int, *, db_path: str | Path = DATABASE_PATH
) -> dict[str, Any] | None:
    """按 ID 读取元数据，不存在时返回 None。"""
    with _connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM data_files WHERE id = ?", (file_id,)
        ).fetchone()
        return dict(row) if row is not None else None


def list_files(
    keyword: str = "",
    category: str | None = None,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> list[dict[str, Any]]:
    """按名称子串、精确分类筛选，按 ID 倒序返回；空分类表示全部。

    instr 将用户输入视为普通文本，百分号、下划线不会成为通配符。
    """
    with _connection(db_path) as connection:
        rows = connection.execute(
            """SELECT * FROM data_files
            WHERE (? = '' OR instr(lower(original_name), lower(?)) > 0
                OR instr(lower(display_name), lower(?)) > 0)
              AND (? IS NULL OR ? = '' OR category = ?)
            ORDER BY id DESC""",
            (keyword, keyword, keyword, category, category, category),
        ).fetchall()
        return [dict(row) for row in rows]


def update_file(
    file_id: int,
    *,
    display_name: str | None = None,
    category: str | None = None,
    description: str | None = None,
    db_path: str | Path = DATABASE_PATH,
) -> bool:
    """修改可编辑信息；None 表示保持原值，空描述可用于清空备注。

    返回记录是否存在。无修改参数时只检查存在性，不修改更新时间。
    """
    if display_name is None and category is None and description is None:
        return get_file(file_id, db_path=db_path) is not None
    with _connection(db_path) as connection:
        cursor = connection.execute(
            """UPDATE data_files SET
                display_name = COALESCE(?, display_name),
                category = COALESCE(?, category),
                description = COALESCE(?, description),
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?""",
            (display_name, category, description, file_id),
        )
        return cursor.rowcount > 0


def delete_file_record(
    file_id: int, *, db_path: str | Path = DATABASE_PATH
) -> bool:
    """仅删除元数据；成功返回 True，不存在返回 False。

    不操作磁盘文件。后续文件管理模块须协调文件删除与数据库事务。
    数据库不可写或被锁定等失败会抛出 sqlite3.Error，不伪报成功。
    """
    with _connection(db_path) as connection:
        cursor = connection.execute("DELETE FROM data_files WHERE id = ?", (file_id,))
        return cursor.rowcount > 0


def get_dashboard_stats(
    *, db_path: str | Path = DATABASE_PATH
) -> dict[str, Any]:
    """返回元数据汇总，空库计数为零；不读取文件或计算数据内容。"""
    with _connection(db_path) as connection:
        row = connection.execute(
            """SELECT COUNT(*) AS total_files,
                COALESCE(SUM(file_size), 0) AS total_size,
                COALESCE(SUM(row_count), 0) AS total_rows,
                COUNT(DISTINCT category) AS category_count
            FROM data_files"""
        ).fetchone()
        result = dict(row)
        result["file_type_counts"] = dict.fromkeys(("csv", "tsv", "xlsx"), 0)
        for item in connection.execute(
            "SELECT file_type, COUNT(*) AS count FROM data_files GROUP BY file_type"
        ):
            result["file_type_counts"][item["file_type"]] = item["count"]
        return result
