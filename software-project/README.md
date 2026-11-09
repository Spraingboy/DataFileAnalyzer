# 多格式数据文件管理与统计分析系统 V1.0

DataFileAnalyzer 是使用 Python、Streamlit、Pandas、SQLite、Plotly 和 OpenPyXL 的本地单用户工具。六个页面为：系统概览、文件管理、数据预览、统计分析、数据可视化、数据导出。不包含登录、权限、云服务、机器学习或额外数据库。

完整操作流程、输入输出规则、常见问题、截图占位与人工验收表见 [用户使用说明书](docs/用户使用说明书.md)。说明书不嵌入软件截图，待使用者从真实运行的软件中自行截取。

## 安装与启动

目标 Python 版本为 **3.11**。本机现有虚拟环境使用 Python 3.13.2，完整实测环境及未执行项见 [TEST_REPORT.md](TEST_REPORT.md)。SQLite 使用 Python 标准库，无需安装数据库服务。

在项目根目录执行以下 PowerShell 命令。首次安装前先确认 `python --version`；已有虚拟环境时可直接使用其解释器。

```powershell
cd D:/codex/software-project
python --version
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -X utf8 -m streamlit run app.py --server.address 127.0.0.1
```

浏览器访问 <http://127.0.0.1:8501>。端口被占用时追加 `--server.port 8502` 并访问对应端口。按 Ctrl+C 停止服务；不需要激活虚拟环境或修改 PowerShell 执行策略。macOS/Linux 将解释器路径换为 `.venv/bin/python`。

`requirements.txt` 固定本次验收的直接依赖：Streamlit 1.66.1、Pandas 2.3.3、Plotly 6.9.0、OpenPyXL 3.1.5、Pytest 8.4.2。传递依赖仍由 pip 解析。

## 六个页面

| 页面 | 功能 |
| --- | --- |
| 系统概览 | 真实文件数、总行数、存储空间、支持格式数，文件格式/分类分布及最近上传文件 |
| 文件管理 | 单文件导入、名称搜索、类型/分类组合筛选、名称/分类/备注编辑、二次确认删除 |
| 数据预览 | 选择文件、前 20/50/100 行、实际行列数、字段名称/类型、按选中字段预览 |
| 统计分析 | 概要指标与四个选项卡：数值统计、缺失值分析、重复值分析、分类频次分析 |
| 数据可视化 | 分类频次柱状图、记录顺序折线图、数值分布直方图、双数值散点图；统一英文图表标题与坐标 |
| 数据导出 | 原始文件、所选列 CSV/XLSX、所选字段的数值统计和缺失统计 CSV |

标题与导航名称统一定义在 `config.PAGE_TITLES`。系统概览来自元数据，不通过读取文件重新计算内容统计。界面使用原生 Streamlit 控件、浅色主题和集中管理的样式，不依赖外部字体服务或复杂前端框架。

## 文件与数据限制

- CSV、TSV、XLSX；每次导入一个文件，单文件最多 10 × 1024 × 1024 字节。
- 最多 50000 数据行（不含表头）、100 列，刚好达到限制可以导入。
- CSV 使用逗号、TSV 使用制表符，支持 UTF-8、UTF-8-SIG、GB18030。BOM 文件优先 UTF-8-SIG，其余先尝试 UTF-8；纯 ASCII 按 UTF-8 记录。
- 首行为表头。CSV/TSV 检查引号与字段数量；空值需要保留分隔符。引号内换行属于同一记录，真正空白行忽略。
- XLSX 仅读取第一个工作表，使用 OpenPyXL 只读模式并检查声明及实际行列范围。Excel 内部空白行和格式化使用范围可能计入限制。
- 空文件、仅表头、无法解码、异常字段数量、损坏或加密的 Excel 会拒绝导入并显示原因。

原始名称只进入元数据。真实文件以 UUID 名称保存到 `data/uploads/`，保留原始字节。数据库只保存文件元数据，默认路径为 `data/metadata.db`。首次运行自动创建目录、数据库和 `data_files` 表，重新启动不清空数据；路径相对于项目位置计算。

## 统计与图表口径

1. `None`、`NaN`、`pd.NA`、空字符串及纯空白字符串视为缺失；字面文本 `NA`、`N/A`、`null` 不自动视为缺失。重复或空白字段名生成唯一名称，不修改磁盘文件。
2. 文本列仅在非缺失值全部可转换为数值时识别为数值列。混合文本列保留为分类字段，不静默丢弃不匹配的值。布尔、日期、时间间隔和显式分类类型不强制转换。
3. 数值统计包括有限有效值数量、均值、中位数、最大/最小值、样本标准差（`ddof=1`）。缺失与正负无穷不参与数值聚合；全空数值列有效数量为 0，其余结果为空。标准差少于两项或结果超出浮点可表示范围时为空。
4. 极大有限数值使用标准库 `statistics` 的稳定累加算法，避免中间求和或平方溢出。
5. 每列缺失率以全部数据行数为分母，整体缺失率以全部单元格数为分母。纯函数返回 0～1 比例，界面显示百分比；无数据行时比例未定义，显示“—”。
6. 重复行数为规范化后整行相同、首次出现以外的记录数。同一行出现三次计为 2；不同缺失标记统一处理。
7. 分类统计排除缺失值，统计页显示前 10 项；柱状图展示全部分类频次。
8. 数值图只接受含有限值的数值字段，分类图只接受非空分类字段。散点图使用两个不同的数值字段，并仅保留同时有效的记录。
9. 折线横轴为从 1 开始的原始记录序号。折线/散点图过滤无效值后超过 2000 点，按固定间隔抽取 2000 点，保留首尾及顺序；界面明确提示。直方图不抽样，目标分箱数为 30。
10. **所有统计与导出均使用全部记录，不受图表抽样或预览行数影响。**

## 导出操作

“数据导出”页选择文件后，可直接“下载原始文件”，字节与原编码保持不变，原 XLSX 工作簿整体保留。

派生导出先选择字段与顺序、选择格式，再点击“生成下载文件”，生成成功后点击“下载生成文件”：

- 所选列 CSV：UTF-8-SIG，无额外索引。
- 所选列 XLSX：使用 `BytesIO` 在内存生成“数据”工作表，不向上传目录写入导出文件。
- 数值统计 CSV：仅包含所选字段中的数值字段。
- 缺失值统计 CSV：按照所选字段顺序输出，缺失率为 0～1 比例。

选列导出保留读取到的原始单元格值和用户选择顺序，不把预览类型推断写回数据。例如 CSV 中的编号 `001` 导出仍为文本 `001`。等号开头的 XLSX 导出文本保持文本类型；超过 Excel 单元格 32767 字符上限时明确拒绝，避免静默截断，可改用 CSV。

切换文件、字段、格式、离开导出页或原文件内容改变后，旧生成结果失效。下载内容是生成/展示时验证的快照。原文件存在但内容损坏时仍可下载原始字节，派生导出显示错误；文件已丢失时不展示下载按钮。

## 状态、异常与一致性

- 导入成功后清空上传控件；普通重运行和新会话不重复导入。
- 编辑成功后表单同步数据库中的规范化名称、分类和备注。分类留空保存为“未分类”。
- 删除必须再次确认；取消、切换所选文件或离开页面会清除确认状态。
- 校验通过后以排他方式创建 UUID 文件。保存中断或数据库插入失败时清理本次文件，不覆盖或删除既有文件。
- 磁盘删除失败保留记录；数据库删除失败尝试恢复原始字节。操作系统同时拒绝清理或恢复时明确显示错误及相关 UUID，不伪报成功。
- 文件丢失、内容损坏、没有数值列、全空字段、无成对有效值和导出失败显示中文提示。
- 解析、统计、图表及导出使用有界缓存。页面每次先检查原文件并读取实际字节，再按完整字节内容查询缓存，避免沿用删除或变化前的结果。
- SQLite 与磁盘之间采用正常异常下的失败补偿，不承诺进程崩溃或断电时的跨介质原子事务。

## 项目结构与接口

```text
app.py                      入口、初始化、六页导航和跨页状态清理
config.py                   标题、路径、格式与产品限制
core/
  database.py               SQLite 元数据增删改查与首页概况
  file_service.py           导入、筛选、编辑、删除及失败补偿
  data_reader.py            编码、CSV/TSV/XLSX 读取及限制校验
  dataset_service.py        只读加载上传文件、UUID/路径/存在性检查
  analysis_service.py       纯 DataFrame 预览、类型、统计和频次函数
  chart_service.py          Plotly Express 图表、字段校验与抽样
  export_service.py         CSV/XLSX/统计结果的 bytes 导出
ui/
  dashboard.py              系统概览
  file_manager.py           文件管理
  data_preview.py           兼容的数据预览 render() 入口
  statistics.py             兼容的统计分析 render() 入口
  analysis_page.py          共用读取、缓存、预览和统计界面
  charts.py                 图表界面
  export.py                 导出界面
  components.py             统一页头、卡片、空状态和 Plotly 展示样式
.streamlit/config.toml       官方主题、字体、颜色和控件圆角
assets/styles.css           集中管理自有容器、导航与响应式补充样式
docs/用户使用说明书.md        六个模块的操作步骤、截图占位及人工验收表
tests/                      单元测试、AppTest 与最终整合测试
data/uploads/               UUID 原始文件
data/metadata.db             首次启动创建，只有元数据
requirements.txt            固定的直接依赖
pytest.ini                  Pytest 路径配置
TEST_REPORT.md              最终检查矩阵、实际结果与未执行项
```

既有数据库接口保持不变：`init_database`、`insert_file`、`get_file`、`list_files`、`update_file`、`delete_file_record`、`get_dashboard_stats`。均可通过 `db_path=` 使用独立数据库；查询使用参数化 SQL。

`list_files(keyword="", category=None, *, db_path=...)` 返回按 ID 倒序的字典列表，名称普通子串搜索、分类精确匹配。类型筛选在文件服务层完成。`update_file` 只编辑展示名称、分类和备注。`delete_file_record` 只删除记录，磁盘协调由文件服务完成。不存在的记录读取返回 `None`，更新/删除返回 `False`。

元数据包括原始名称、展示名称、UUID 存储名称、类型、字节大小、行列数、分类、备注、编码和时间。上传时间保存在 `created_at`，时间为 UTC；行数不含表头。

`analysis_service` 的 `prepare_dataframe`、`preview_dataframe`、`field_info`、`dataset_overview`、`numeric_statistics`、`missing_statistics`、`duplicate_row_count`、`category_frequencies`、`analyze_dataframe` 接收 DataFrame 且不修改输入，返回字典、整数或表格。报告包含 `overview/fields/numeric/missing/categorical`。

`chart_service.build_chart(frame, chart_type, x, y=None)` 返回含 Figure、有效记录数、显示项数及抽样标志的结果。`export_service` 的四个导出函数均接收 `(frame, columns)` 并返回 `bytes`。六个页面保留无参数 `render()` 入口。

## 测试与手动验收

```powershell
# 完整测试，中文输出使用 UTF-8
./.venv/Scripts/python.exe -X utf8 -m pytest -q

# 严格模式：把 Python 警告作为错误
./.venv/Scripts/python.exe -X utf8 -m pytest -q -W error

# 最终整合：上传到六页、导出、新会话/独立进程持久化、删除、异常与组合上限
./.venv/Scripts/python.exe -X utf8 -m pytest tests/test_final_integration.py -q

# 核对当前安装的依赖
./.venv/Scripts/python.exe -m pip check
```

测试使用临时文件和临时 SQLite，不向真实上传目录放入样例数据。详细实际结果、覆盖矩阵和无法执行的检查见 [TEST_REPORT.md](TEST_REPORT.md)，不把语法检查视为目标解释器下的运行验证。

## V1.0 功能完成清单

- [x] 六页原生导航与统一标题、主题和卡片布局。
- [x] 系统概览、文件格式/分类分布及最近上传记录，均使用真实元数据。
- [x] CSV/TSV/XLSX 导入、编码与限制校验、UUID 文件保存、SQLite 元数据持久化。
- [x] 名称搜索、类型/分类筛选、编辑、二次确认删除及失败补偿。
- [x] 前 20/50/100 行预览、字段选择、名称/类型及数据概要。
- [x] 数值统计、缺失值统计、重复行检测、分类前 10 项频次。
- [x] 四种 Plotly 图表、适用字段校验及超过 2000 个有效点的折线/散点抽样。
- [x] 原文件、所选列 CSV/XLSX、数值/缺失统计 CSV 下载，统计与导出使用全量记录。
- [x] 空数据、无数值列、文件丢失/损坏、导出失败和重运行状态的自动化回归。

## 已知限制与最终人工验收

目标 Python 3.11 的完整运行仍待验证，现有实测解释器为 Python 3.13.2。单用户本地使用，不提供认证、跨用户隔离或跨磁盘/数据库的崩溃原子事务。产品格式、大小和行列上限见上文；公式取值以读取到的缓存值为准，不负责重新计算 Excel 公式。

当前自动化测试不能替代六页的完整人工视觉验收、浏览器实际保存下载文件及不同操作系统的验证。说明书只列截图占位；请从实际运行软件中补图，不使用生成图或模拟界面作为证明。

建议顺序：启动和空状态 → 三格式/三编码导入 → 搜索筛选和编辑 → 预览与统计核对 → 四种图表及抽样 → 五类下载与回读 → 跨页/刷新/重启 → 异常文件 → 取消/确认删除 → 真实截图归档。详细的通过标准与记录表见 [用户使用说明书](docs/用户使用说明书.md)。

