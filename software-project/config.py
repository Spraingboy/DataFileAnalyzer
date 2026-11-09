"""应用配置：所有数据路径均相对于项目目录。"""

from pathlib import Path

APP_NAME = "多格式数据文件管理与统计分析系统"
APP_VERSION = "V1.0"
PAGE_TITLES = {
    "dashboard": "系统概览", "file_manager": "文件管理", "data_preview": "数据预览",
    "statistics": "统计分析", "charts": "数据可视化", "export": "数据导出",
}
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_PATH = DATA_DIR / "metadata.db"

MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_DATA_ROWS = 50_000
MAX_DATA_COLUMNS = 100
SUPPORTED_EXTENSIONS = ("csv", "tsv", "xlsx")
SUPPORTED_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030")
EXCEL_SHEET_INDEX = 0


def ensure_data_directories() -> None:
    """启动时创建数据目录，不依赖当前工作目录。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
