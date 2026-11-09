"""协调文件与元数据操作，保持 database 接口不变。"""

import logging
import re
import sqlite3
from pathlib import Path, PureWindowsPath
from uuid import UUID, uuid4

import config
from core import database
from core.data_reader import DataReadError, read_data

logger = logging.getLogger(__name__)


class FileServiceError(Exception):
    """可向界面展示的文件操作错误。"""


class FileService:
    def __init__(self, upload_dir=None, db_path=None):
        self.upload_dir = Path(upload_dir if upload_dir is not None else config.UPLOAD_DIR)
        self.db_path = Path(db_path if db_path is not None else config.DATABASE_PATH)

    @staticmethod
    def _editable(display_name, category, description):
        if not display_name.strip():
            raise FileServiceError("展示名称不能为空。")
        return display_name.strip(), category.strip() or "未分类", description.strip()

    def import_file(
        self, original_name: str, content: bytes, *, display_name: str = "",
        category: str = "未分类", description: str = "",
    ) -> int:
        if not original_name.strip() or "\x00" in original_name:
            raise FileServiceError("文件名称无效。")
        file_type = PureWindowsPath(original_name).suffix.lower().lstrip(".")
        display_name, category, description = self._editable(
            display_name or original_name, category, description
        )
        try:
            result = read_data(content, file_type)
        except DataReadError as exc:
            raise FileServiceError(str(exc)) from exc
        # 原始名称只进入元数据，真实路径完全由 UUID 与受信任扩展名组成。
        stored_name = f"{uuid4().hex}.{file_type}"
        target = self.upload_dir / stored_name
        created = False
        try:
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                created = True
                handle.write(content)
            return database.insert_file(
                original_name, stored_name, file_type, len(content),
                row_count=len(result.frame), column_count=len(result.frame.columns),
                display_name=display_name, category=category, description=description,
                encoding=result.encoding, db_path=self.db_path,
            )
        except Exception as exc:
            logger.exception("导入文件失败")
            if created:
                try:
                    target.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    raise FileServiceError(
                        f"导入失败且残留文件清理失败：{stored_name}。请检查目录权限后清理。"
                    ) from cleanup_error
            raise FileServiceError("文件保存或数据库写入失败，请检查磁盘空间及目录、数据库权限。") from exc

    def list_files(self, keyword="", category=None, file_type=None):
        try:
            records = database.list_files(keyword, category, db_path=self.db_path)
        except (OSError, sqlite3.Error) as exc:
            raise FileServiceError("文件列表读取失败，请检查数据库状态。") from exc
        return [record for record in records if file_type is None or record["file_type"] == file_type]

    def update_file(self, file_id, *, display_name, category, description):
        display_name, category, description = self._editable(display_name, category, description)
        try:
            updated = database.update_file(
                file_id, display_name=display_name, category=category,
                description=description, db_path=self.db_path,
            )
        except (OSError, sqlite3.Error) as exc:
            raise FileServiceError("文件信息保存失败，请检查数据库状态。") from exc
        if not updated:
            raise FileServiceError("文件记录不存在，请刷新列表。")

    def _stored_path(self, stored_name):
        # 验证数据库中的名称，旧记录和异常记录也不能越过上传目录。
        if not re.fullmatch(r"[0-9a-fA-F-]{32,36}\.(csv|tsv|xlsx)", stored_name):
            raise FileServiceError("记录中的存储名称无效，已停止文件操作。")
        try:
            UUID(stored_name.rsplit(".", 1)[0])
        except ValueError as exc:
            raise FileServiceError("记录中的 UUID 无效，已停止文件操作。") from exc
        root = self.upload_dir.resolve()
        path = root / stored_name
        if path.is_symlink() or path.resolve().parent != root:
            raise FileServiceError("文件路径异常，已停止文件操作。")
        return path

    def delete_file(self, file_id: int) -> str:
        """磁盘删除失败不删记录；数据库删除失败时用原始字节恢复文件。

        这是正常异常下的失败补偿，不是跨 SQLite/磁盘的崩溃原子事务。
        """
        try:
            record = database.get_file(file_id, db_path=self.db_path)
            if record is None:
                raise FileServiceError("文件记录不存在，请刷新列表。")
            path = self._stored_path(record["stored_name"])
            backup = None
            try:
                with path.open("rb") as handle:
                    backup = handle.read(config.MAX_FILE_SIZE_BYTES + 1)
                if len(backup) > config.MAX_FILE_SIZE_BYTES:
                    raise FileServiceError("磁盘文件大小异常，无法安全备份删除。")
                path.unlink()
            except FileNotFoundError:
                backup = None
            try:
                if not database.delete_file_record(file_id, db_path=self.db_path):
                    raise FileServiceError("文件记录不存在，请刷新列表。")
            except Exception as exc:
                if backup is not None:
                    try:
                        with path.open("xb") as handle:
                            handle.write(backup)
                    except OSError as restore_error:
                        logger.exception("删除失败后恢复文件失败")
                        raise FileServiceError(
                            f"数据库删除失败，文件恢复也失败：{path.name}。请检查磁盘及权限。"
                        ) from restore_error
                raise FileServiceError("数据库删除失败，原始文件已保留或恢复。") from exc
            return "文件及记录已删除。" if backup is not None else "原始文件已缺失，已清理数据库记录。"
        except FileServiceError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise FileServiceError("删除失败，数据库记录已保留，请检查文件及数据库权限。") from exc
