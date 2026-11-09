# V1.0 最终整合与测试报告

验收日期：2026-11-05（Asia/Shanghai）。项目目录：`D:/codex/software-project`。

## 2026-11-06 文档整理与回归复核

以下为当前代码在文档整理时重新执行的结果；后续各节保留 2026-11-05 最终整合的历史记录。

| 检查 | 本次实际结果 |
| --- | --- |
| `./.venv/Scripts/python.exe -X utf8 -m pytest -q -W error` | **162 passed in 27.03s**，退出码 0，无跳过 |
| `./.venv/Scripts/python.exe -m pip check` | `No broken requirements found.` |
| README、requirements 与使用说明书 | 已按当前六页菜单、依赖版本、实际统计/图表/导出规则核对 |
| 软件截图 | 使用说明书仅提供文字占位，不插入或生成软件截图，待用户实际运行后补充 |

实测解释器仍为 Python 3.13.2，未在 Python 3.11 中运行完整测试。本次文档整理未执行六页完整浏览器人工验收或浏览器实际保存下载文件；自动化通过不能替代这些检查。人工验收步骤、统计核对样例和记录栏见 `docs/用户使用说明书.md` 第 15 节。

## 实际执行结果

| 检查 | 实际结果 |
| --- | --- |
| 完整严格回归：`python -X utf8 -m pytest -q -W error` | **162 passed in 24.61s**，退出码 0，无跳过或告警 |
| 最终整合测试 | 包含在上述完整回归中；覆盖真实上传控件、六页、导出、新会话/独立进程持久化及删除 |
| Python 3.11 语法规则解析 | 31 个项目 Python 文件通过；这是语法检查，不是 Python 3.11 运行验证 |
| `pip check` | `No broken requirements found.`，退出码 0 |
| 固定依赖离线核对：`pip install --dry-run --no-index -r requirements.txt` | 全部直接依赖及其安装依赖已满足，退出码 0 |
| 本地 Streamlit 实际启动 | 在 `127.0.0.1:18501` 成功启动；首页 HTTP 200，`/_stcore/health` HTTP 200、正文 `ok`；验收后停止 |
| 组合产品上限 | 真实 CSV 字节不超过 10MB，50000 行 × 100 列导入及统计通过；各列有效数 50000、均值 4.5，重复行 49990 |
| 独立 DataFrame 规模检查 | 50000 行 × 100 个浮点数值字段，100 行统计结果、有效数量及均值断言通过，单次约 6.83 秒；不是性能承诺 |

实测环境：Windows、Python 3.13.2、Streamlit 1.66.1、Pandas 2.3.3、Plotly 6.9.0、OpenPyXL 3.1.5、Pytest 8.4.2。SQLite、csv、io、statistics 为 Python 标准库。

测试使用临时目录与临时 SQLite。真实 `data/uploads/` 在验收后仅含原有 `.gitkeep`，未放入示例业务文件。

## 覆盖矩阵

| 范围 | 验证内容 | 测试模块 |
| --- | --- | --- |
| 六页导航与标题 | 固定六个菜单，标题与菜单一致，空库提示、首页真实元数据概况、初始化失败提示 | `test_navigation.py`、`test_final_integration.py` |
| SQLite | 初始化幂等、增删改查、参数化查询、字段更新范围、元数据汇总、完整性检查；新 Streamlit 会话和新 Python 进程仍能读取记录 | `test_database.py`、`test_final_integration.py` |
| 输入格式与编码 | CSV/TSV 各三种编码经真实上传控件导入；XLSX 只读取第一表 | `test_data_reader.py`、`test_dataset_service.py`、`test_final_integration.py` |
| 限制与异常格式 | 10MB、50000 行、100 列边界；三项组合上限；空文件、仅表头、错误编码、引号/列数异常、损坏 Excel、虚假工作表尺寸 | `test_data_reader.py`、`test_file_service.py`、`test_final_integration.py` |
| 文件一致性 | UUID 保存、原始字节保留、同名文件、碰撞不覆盖、插入失败清理、磁盘删除失败保留记录、数据库删除失败恢复文件、恢复/清理再次失败明确报错 | `test_file_service.py`、`test_file_manager_ui.py` |
| 管理与重运行 | 搜索、组合筛选、编辑、取消/确认删除、成功后清空上传控件；反复重运行不重复导入；跨页清除删除意图；表单与规范化元数据同步 | `test_file_manager_ui.py`、`test_final_integration.py` |
| 预览 | 20/50/100 行、字段名称/类型、字段选择、切换文件、文件结构变化、文件缺失或损坏时不显示旧缓存 | `test_analysis_ui.py` |
| 统计 | 已知均值、中位数、样本标准差、缺失数量/率、重复行、前 10 项频次；无数值列、全空列、布尔/日期/时间间隔、混合文本、嵌套值、极大有限数值 | `test_analysis_service.py`、`test_analysis_ui.py` |
| 图表 | 四种 Plotly Express 图表与 `st.plotly_chart`；适用字段限制、成对有效值、记录顺序；1999/2000/2001/5000 点抽样边界和首尾；柱状图及直方图使用全量有效值 | `test_chart_service.py`、`test_visual_export_ui.py` |
| 导出 | 原始字节、CSV BOM/中文/换行/引号、所选字段及顺序、前导零、XLSX 回读和公式状文本、Excel 长文本拒绝、数值/缺失统计 CSV | `test_export_service.py`、`test_visual_export_ui.py` |
| 导出状态 | 切换文件/字段/格式/页面、文件内容或结构变化后旧结果失效；缺失文件不再显示下载；损坏文件仍可下载原字节 | `test_visual_export_ui.py`、`test_final_integration.py` |
| 全流程 | 七组输入（CSV/TSV 三编码 + XLSX）分别经上传→六页→四图→四类派生导出→新会话→删除→空库；文件数量与记录一致 | `test_final_integration.py` |

故障处理既使用真实 SQLite 触发器拒绝插入/删除，也使用异常注入模拟磁盘空间、权限、序列化及恢复失败。AppTest 中记录传给真实 `st.plotly_chart` / `st.download_button` 的 Figure 和字节，并重新读取 CSV/XLSX 核对内容，不用虚构数据替代产品计算。

## 本次修复与整合

1. 离开文件管理后再返回，旧的删除确认状态仍存在：导航切换时清除删除意图。
2. 编辑保存后，表单仍显示多余空格或空分类，和数据库规范化值不一致：按元数据快照同步表单，成功保存后重新初始化显示值。
3. 大但有限的数值（例如两个 `1e308`）导致均值、中位数、标准差中间溢出：改用标准库稳定累加与样本标准差。常数样本均值为 `1e308`、标准差为 0；确实超出浮点范围的结果显示为空。
4. 三处测试数据库连接未显式关闭，严格告警模式出现 ResourceWarning：测试使用 `closing` 明确关闭，生产数据库连接原本已有 `finally` 关闭。
5. 首页接入已存在的 `get_dashboard_stats`，移除遗留占位提示；集中六页标题，去除菜单中的开发阶段文案。
6. requirements 固定已验收的直接依赖，README 整理为最终用户说明；文件管理与数据库接口保持兼容。

预览页在原文件结构改变后会清除失效字段，新增回归测试确认了这一行为，无需修改其现有逻辑。

## 未执行与实际限制

| 检查 | 状态与原因 |
| --- | --- |
| Python 3.11 解释器下完整测试 | **未执行**。本机已发现的 SDK/可用解释器只有 Python 3.13.2；不能用 3.11 语法检查替代此项。需要准备 Python 3.11 独立虚拟环境后运行同一完整命令。 |
| 浏览器人工逐项点击、Plotly WebGL/画面检查、操作系统保存下载文件 | **未执行人工验收**。已执行 AppTest 控件与数据链路检查、导出内容回读和真实 HTTP 启动检查，不将其描述为浏览器人工验收。 |
| 其他操作系统 | 未执行，当前实测为 Windows。 |
| 实机断电、杀进程、物理磁盘满、Windows ACL 故障 | 未做破坏性实机测试。正常异常补偿已通过触发器和异常注入验证；实现不承诺磁盘/SQLite 的崩溃原子提交。 |

## 复现命令

```powershell
cd D:/codex/software-project
./.venv/Scripts/python.exe -X utf8 -m pytest -q -W error
./.venv/Scripts/python.exe -X utf8 -m pytest tests/test_final_integration.py -q
./.venv/Scripts/python.exe -m pip check
./.venv/Scripts/python.exe -m pip install --dry-run --no-index -r requirements.txt
```

## 本阶段涉及文件

- `app.py`、`config.py`：统一标题、稳定菜单、跨页状态清理。
- `core/analysis_service.py`：数值稳定性修复，输出结构不变。
- `ui/dashboard.py`、`ui/file_manager.py`、`ui/analysis_page.py`、`ui/charts.py`、`ui/export.py`：概况接入、表单状态、共用标题和字段提示。
- `tests/test_file_manager_ui.py`、`tests/test_analysis_ui.py`、`tests/test_analysis_service.py`：新增回归用例。
- `tests/test_database.py`、`tests/test_file_service.py`：显式关闭故障测试的数据库连接。
- `tests/test_final_integration.py`：新增最终整合测试和组合上限验证。
- `requirements.txt`、`README.md`、`TEST_REPORT.md`：最终依赖、操作说明、验收报告。
