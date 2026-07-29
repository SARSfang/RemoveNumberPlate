# 子 Spec 3：项目/客户预设与归档设计

> 日期：2026-07-29
> 状态：待评审
> 所属总纲：[2026-07-29-v0.3.0-master-design.md](./2026-07-29-v0.3.0-master-design.md)
> 推进顺序：第 3 项（共 7 项）
> 依赖：子 spec 1（监视文件夹）已实现；子 spec 2（批量后处理）已实现
> （`NamingTemplate` 的 `{client}` 占位符、`post_process_config` 结构均已就绪）

---

## 1. 版本与范围

本子 spec 实现 v0.3.0 总纲中的"项目/客户预设与归档"功能。摄影师经常在
多个客户 / 拍摄项目之间切换，每个客户对边缘扩展、输出命名、水印、归档目录
都有不同要求。当前所有参数只能存为全局 `settings.json`，切换客户时需要手动
逐项改回，易错且耗时。本子 spec 引入"项目"作为预设容器，切换项目时一键套用
全部参数，并把后续产生的任务归属到该项目，便于历史按项目归档与检索。

**在范围内**：

- `ProjectStore`（SQLite 持久层，与 `jobs.sqlite3` 同库）
- `ProjectPreset` dataclass（处理参数 + 后处理配置 + 输出目录规则）
- `jobs.sqlite3` schema v6 → v7（新增 `projects` 表、`jobs.project_id` 外键）
- `UserSettings` 扩展（`current_project_id` 字段）
- `WatchFolder` 扩展（可选 `project_id`，兑现子 spec 1 推迟的预设绑定）
- 批处理页顶部"当前项目"选择器
- 项目管理对话框（CRUD）+ 预设导入 / 导出
- 后端桥接白名单 API（`list_projects` 等 5 个方法）
- `BatchService` 入队时打 `project_id` 标签 + 套用项目预设

**不在范围内**：

- 跨机器项目同步（留给后续版本，导入 / 导出已覆盖单机迁移）
- 项目级模型选择（仍用全局模型，留给 v0.4）
- 项目级权限 / 多用户（单机单用户产品定位）
- 项目归档压缩包导出（仅做"按项目筛选历史"，打包留给 v0.4）

---

## 2. 已确认需求决策

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 预设粒度 | 单个项目承载一整套预设（处理 + 后处理 + 输出目录），不再拆子预设 |
| 2 | 切换语义 | 切换项目立即套用全部参数；运行中的批次不中断，下一张起生效 |
| 3 | 默认项目 | 不强制选项目；"无项目"是合法状态，沿用全局 `settings.json` 行为 |
| 4 | 旧任务归属 | 旧 job 的 `project_id` 为 NULL，正常显示，不强制回填 |
| 5 | 删除项目 | 软删除可选不做；硬删除时关联 job 的 `project_id` 置 NULL（`ON DELETE SET NULL`） |
| 6 | 监视文件夹绑定 | 复用本 spec 落地子 spec 1 推迟的 `preset_id`：WatchFolder 可选绑定一个项目 |
| 7 | 导入 / 导出格式 | 单个 `.json` 文件（ProjectPreset 序列化），不含项目 id / 时间戳 |
| 8 | 项目名唯一性 | 名称允许重复（以 id 为准），但 UI 创建时若重名给出软提示 |
| 9 | 输出目录规则 | 三种模式：源文件旁（默认）/ 项目子文件夹 / 固定目录 |
| 10 | 历史归属展示 | 历史列表新增"项目"列（可空），用于子 spec 4 的按项目分组 |

---

## 3. 架构概览

### 3.1 实现方案

采用**方案 1：ProjectStore + UserSettings.current_project_id + BatchService 套用钩子**。

```
┌─ app/desktop.py ─────────────────────────────────────────────┐
│  DesktopApi                                                  │
│    ├─ ProjectStore (新, app/core/project_store.py)           │
│    │    CRUD projects, 持久化到 jobs.sqlite3                 │
│    │                                                         │
│    ├─ BatchService (扩展)                                    │
│    │    create_job 前注入 project_id                          │
│    │    start 前套用当前项目预设 (preset/margin/post/输出)    │
│    │                                                         │
│    └─ WatchFolderService (扩展)                              │
│         WatchFolder.project_id → 入队时覆盖 current_project   │
└─────────────────────────────────────────────────────────────┘

┌─ app/core/ ──────────────────────────────────────────────────┐
│  job_store.py (扩展)                                        │
│    schema v6 → v7: 新增 projects 表, jobs.project_id 外键   │
│    StoredJob 新增 project_id 字段                           │
│  project_store.py (新)                                      │
│    ProjectPreset dataclass + ProjectStore CRUD              │
│  settings.py (扩展)                                         │
│    UserSettings 新增 current_project_id                      │
│    WatchFolder 新增 project_id (可空)                        │
└─────────────────────────────────────────────────────────────┘

┌─ app/web/ ──────────────────────────────────────────────────┐
│  batch/workspace.js (扩展)                                  │
│    顶部命令栏新增"当前项目"选择器                            │
│  projects/ (新目录)                                         │
│    project-picker.js   选择器                               │
│    project-dialog.js   CRUD 对话框 + 导入/导出              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 组件职责与依赖方向

- `ProjectStore`：只负责"项目记录的 CRUD + 预设序列化"，不处理图片、不套用参数
- `JobStore`：负责 schema 迁移与 `jobs.project_id` 的读写（归属查询）
- `DesktopApi`：负责"切换项目 → 调用现有 `set_preset` / `set_mask_margin` /
  `set_post_process_config` 套用参数"，是唯一知道"如何套用"的协调者
- `BatchService`：入队时接收 `project_id` 并透传到 `create_job`
- 前端：只负责选择器与 CRUD UI，不直接拼接参数

**关键设计原则**：ProjectStore 不知道"参数怎么用"，DesktopApi 不知道"参数怎么存"——
单向依赖，套用逻辑集中在 DesktopApi 复用已有 setter。

### 3.3 方案对比（已评估）

| 方案 | 描述 | 评价 |
|---|---|---|
| **方案 1（采纳）** | ProjectStore + current_project_id + BatchService 套用钩子 | 复用已有 setter；schema 集中迁移；前端改动最小 |
| 方案 2 | 每个项目独立 settings.json 文件 | 文件数膨胀；切换需重载 SettingsStore；与 JobStore 归属割裂 |
| 方案 3 | 全部塞进 settings.json 的 projects 数组 | settings.json 膨胀；无法用 SQL 按项目查历史；与 jobs 库分离 |

---

## 4. ProjectPreset 数据模型

### 4.1 dataclass 定义

```python
@dataclass(frozen=True, slots=True)
class OutputDirectoryRule:
    """输出目录规则。mode 决定输出落盘位置。"""

    mode: str = "beside_source"  # "beside_source" | "project_subfolder" | "fixed_directory"
    subfolder_name: str = ""     # project_subfolder 模式下的子文件夹名
    fixed_directory: str = ""    # fixed_directory 模式下的绝对路径

    def __post_init__(self) -> None:
        if self.mode not in ("beside_source", "project_subfolder", "fixed_directory"):
            raise ValueError(f"unknown output directory mode: {self.mode}")
        if self.mode == "fixed_directory" and not self.fixed_directory.strip():
            raise ValueError("fixed_directory mode requires fixed_directory")
        # 非法字符过滤延后到实际拼路径时，dataclass 只做模式校验


@dataclass(frozen=True, slots=True)
class ProjectPreset:
    """单个项目/客户承载的完整预设。"""

    name: str
    preset: str                       # 处理预设: "fast" | "balanced" | "strict"
    mask_margin_ratio: float          # 边缘扩展比例 (0.0 ~ 由 mask_builder 上下界决定)
    post_process_config: Mapping[str, object]  # 与子 spec 2 的 post_process_config 同构
    output_directory_rule: OutputDirectoryRule

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("project name must be a non-empty string")
        if self.preset not in PRESETS:
            raise ValueError(f"unknown processing preset: {self.preset}")
        if (isinstance(self.mask_margin_ratio, bool)
                or not isinstance(self.mask_margin_ratio, (int, float))
                or not isfinite(self.mask_margin_ratio)
                or not MINIMUM_MARGIN_RATIO
                <= self.mask_margin_ratio
                <= MAXIMUM_MARGIN_RATIO):
            raise ValueError(
                f"mask margin must be between {MINIMUM_MARGIN_RATIO} "
                f"and {MAXIMUM_MARGIN_RATIO}"
            )
        if not isinstance(self.post_process_config, Mapping):
            raise ValueError("post_process_config must be a mapping")
        if not isinstance(self.output_directory_rule, OutputDirectoryRule):
            raise ValueError("output_directory_rule must be an OutputDirectoryRule")
```

> 校验风格沿用 `UserSettings` / `WatchFolder` 的 `__post_init__` fail-fast 模式，
> 不引入 `to_dict` / `from_dict`，序列化在 `ProjectStore` 内联完成。

### 4.2 字段语义

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 项目 / 客户名，允许重复，UI 显示用 |
| `preset` | str | 处理预设，复用 `PRESETS`（fast / balanced / strict） |
| `mask_margin_ratio` | float | 边缘扩展比例，与 `UserSettings.mask_margin_ratio` 同语义 |
| `post_process_config` | Mapping | 与子 spec 2 的 `post_process_config` 同构（enabled / naming_template / watermark / exif） |
| `output_directory_rule` | OutputDirectoryRule | 输出落盘规则 |

### 4.3 输出目录规则三种模式

- **`beside_source`**（默认）：输出到源文件同目录，文件名 `{original}_clean{ext}`，
  与当前行为完全一致。`subfolder_name` / `fixed_directory` 被忽略。
- **`project_subfolder`**：在源文件所在目录下创建 `subfolder_name` 子文件夹，
  输出落入其中。`subfolder_name` 支持占位符 `{project}`（替换为项目名，过滤非法字符）。
  子文件夹不存在时自动创建。
- **`fixed_directory`**：所有输出统一落入 `fixed_directory` 指定的绝对路径。
  路径不存在时自动创建。命名冲突沿用 `NamingTemplate.resolve_conflict` 自增。

> 输出目录规则在 `BatchService._finish_item` 写出文件前生效，覆盖默认输出路径。
> 与子 spec 2 的后处理命名叠加顺序：先定目录 → 再用 `NamingTemplate` 定文件名 →
> 最后 `resolve_conflict`。

---

## 5. 数据模型变更

### 5.1 jobs.sqlite3 schema v6 → v7

schema 迁移集中在 `app/core/job_store.py`（遵循总纲 §3.1）。
`SCHEMA_VERSION` 从 6 升到 7。

新增 `projects` 表：

```sql
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    preset_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
```

`jobs` 表新增 `project_id` 外键（可空，兼容旧任务）：

```sql
ALTER TABLE jobs ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL;
```

> 用 `ON DELETE SET NULL` 而非 `CASCADE`：删除项目不应删除历史任务记录，
> 历史必须保留（合规与可追溯）。项目被删后，关联 job 的 `project_id` 置 NULL，
> 历史列表"项目"列显示为空。

为历史按项目查询预留索引（子 spec 4 会用到）：

```sql
CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);
```

### 5.2 迁移与兼容性

- 旧库 schema v6 → 自动迁移到 v7：`projects` 表用 `CREATE TABLE IF NOT EXISTS`，
  `jobs.project_id` 用 `PRAGMA table_info` 检测后 `ALTER TABLE ADD COLUMN`（沿用
  v3/v4/v5 迁移模式）
- 旧 job 的 `project_id` 为 NULL，正常显示，历史列表"项目"列为空
- 旧库无 `projects` 表时，`list_projects` 返回空列表，"当前项目"选择器显示"无项目"
- 迁移前备份 `jobs.sqlite3.bak-v6`，失败回滚（沿用现有备份机制）

### 5.3 StoredJob 扩展

`StoredJob` 新增 `project_id: str | None = None` 字段，`list_jobs` / `get_job` 的
SELECT 列表与 `_stored_job_from_row` 同步扩展。

### 5.4 settings.json schema

新增 `current_project_id` 字段（可空）：

```json
{
  "preset": "balanced",
  "mask_margin_ratio": 0.35,
  "watch_folders": [
    {
      "path": "D:/商拍/2026-07-客户A",
      "enabled": true,
      "added_at": "2026-07-29T10:30:00Z",
      "project_id": "proj_abc123"
    }
  ],
  "current_project_id": "proj_abc123"
}
```

兼容性：缺失 `current_project_id` 字段时默认 `None`（"无项目"状态）。
`WatchFolder` 新增 `project_id: str | None`，缺失时为 `None`（兑现子 spec 1
决策 8 的推迟项）。

### 5.5 UserSettings / WatchFolder dataclass 扩展

```python
@dataclass(frozen=True, slots=True)
class WatchFolder:
    path: str
    enabled: bool
    added_at: str
    project_id: str | None = None  # 新增，可空

@dataclass(frozen=True, slots=True)
class UserSettings:
    preset: str = DEFAULT_PRESET
    mask_margin_ratio: float = DEFAULT_MARGIN_RATIO
    watch_folders: tuple[WatchFolder, ...] = ()
    current_project_id: str | None = None  # 新增，可空
```

> `project_id` 的存在性校验延后到 `ProjectStore` 读取时（settings 不查库），
> 避免 settings 加载强依赖 jobs.sqlite3。

---

## 6. ProjectStore 详细设计

### 6.1 类接口

```python
class ProjectStore:
    """项目记录持久层。与 JobStore 共享 jobs.sqlite3 文件。"""

    def __init__(self, path: Path) -> None: ...  # 同一 DB 路径，独立连接（WAL）

    # CRUD
    def list_projects(self) -> list[ProjectRecord]: ...
    def get_project(self, project_id: str) -> ProjectRecord: ...
    def create_project(self, preset: ProjectPreset) -> ProjectRecord: ...
    def update_project(self, project_id: str, preset: ProjectPreset) -> ProjectRecord: ...
    def delete_project(self, project_id: str) -> None: ...
    def touch_last_used(self, project_id: str) -> None: ...  # 切换时更新 last_used_at

    # 导入 / 导出
    def export_preset(self, project_id: str) -> str: ...  # 返回 JSON 字符串
    def import_preset(self, json_text: str, new_name: str | None = None) -> ProjectRecord: ...

    def __enter__(self) -> ProjectStore: ...
    def __exit__(self, *_args: object) -> None: ...
```

```python
@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: str
    name: str
    preset: ProjectPreset
    created_at: str
    last_used_at: str | None
```

### 6.2 序列化约定

`preset_json` 列存储 `ProjectPreset` 的 JSON 序列化：

```json
{
  "name": "客户A-商拍",
  "preset": "balanced",
  "mask_margin_ratio": 0.35,
  "post_process_config": {
    "enabled": true,
    "naming_template": "{client}_{seq:03}_{date}.{ext}",
    "watermark": { "enabled": true, "text": "© 客户A", "...": "..." },
    "exif": { "enabled": true, "artist": "工作室", "copyright": "© 2026 客户A" }
  },
  "output_directory_rule": {
    "mode": "project_subfolder",
    "subfolder_name": "{project}/已消除",
    "fixed_directory": ""
  }
}
```

- 导出时只写 `preset_json` 内容（不含 `id` / `created_at` / `last_used_at`），
  导入时生成新 id 与时间戳，`name` 默认取文件中的值，可用 `new_name` 覆盖
- 序列化用 `json.dumps(..., ensure_ascii=False)`，沿用 `mask_revisions` 的中文友好模式
- 反序列化失败时抛 `ValueError`，由 DesktopApi 转为用户可见的 toast

### 6.3 与 JobStore 的连接关系

- `ProjectStore` 独立打开 `jobs.sqlite3`，`PRAGMA journal_mode=WAL`（与 JobStore 一致）
- WAL 模式支持多读单写，ProjectStore 的偶发写与 JobStore 的写互不阻塞读
- 不复用 JobStore 的连接对象：保持模块边界清晰，避免锁传递
- `projects` 表的创建仍由 `JobStore._initialize` 完成（schema 迁移集中原则），
  `ProjectStore` 只读写不建表

---

## 7. 后端桥接扩展

`app/desktop.py` 新增白名单 API（延续总纲 §3.2：只传 id / 配置对象，不接收任意路径
——`fixed_directory` 是配置对象内部字段，受 schema 校验约束，非前端任意拼路径）：

```python
def list_projects(self) -> list[dict[str, object]]:
    """返回所有项目（按 last_used_at DESC, name ASC 排序），含 id/name/created_at/last_used_at。
    不返回 preset 详情（详情按需 get_project）。"""

def create_project(self, preset_json: str) -> dict[str, object]:
    """新建项目。preset_json 为 ProjectPreset 序列化字符串。返回新项目摘要。"""

def update_project(self, project_id: str, preset_json: str) -> dict[str, object]:
    """更新已有项目的预设。project_id 必须存在。"""

def delete_project(self, project_id: str) -> dict[str, object]:
    """删除项目。关联 job 的 project_id 置 NULL（ON DELETE SET NULL）。"""

def set_current_project(self, project_id: str | None) -> dict[str, object]:
    """切换当前项目。传 None 表示切到"无项目"。
    - 套用 preset → 调 set_preset
    - 套用 mask_margin_ratio → 调 set_mask_margin
    - 套用 post_process_config → 调 set_post_process_config
    - 套用 output_directory_rule → 写入 BatchService 输出目录覆盖
    - 写入 settings.current_project_id
    - touch_last_used(project_id)
    运行中的批次不中断，下一张起生效。"""
```

### 7.1 套用逻辑（set_current_project 内部）

```python
def set_current_project(self, project_id: str | None) -> dict[str, object]:
    if project_id is None:
        # 切到"无项目"：不回滚参数（保留当前值），只清空 current_project_id
        self._settings = replace(self._settings, current_project_id=None)
        self._settings_store.save(self._settings)
        self._service.set_output_directory_override(None)
        return {"accepted": True, "message": "已切到无项目状态。"}

    with ProjectStore(self._job_database) as store:
        record = store.get_project(project_id)
        preset = record.preset

    # 复用现有 setter（含批次运行中拒绝逻辑与持久化）
    preset_result = self.set_preset(preset.preset)
    margin_result = self.set_mask_margin(round(preset.mask_margin_ratio * 100))
    # post_process_config 套用沿用子 spec 2 的 setter
    pp_result = self.set_post_process_config(dict(preset.post_process_config))

    # 输出目录覆盖（BatchService 新增方法）
    self._service.set_output_directory_override(preset.output_directory_rule)

    self._settings = replace(self._settings, current_project_id=project_id)
    self._settings_store.save(self._settings)

    with ProjectStore(self._job_database) as store:
        store.touch_last_used(project_id)

    return {"accepted": True, "message": f"已切换到项目「{preset.name}」。"}
```

> 若 `set_preset` 因批次运行中返回 `accepted: False`，不阻塞切换：参数会在
> 下一张起通过 `replace_processor_factory` 重试路径生效；UI 给出软提示
> "部分参数将在当前批次结束后生效"。

### 7.2 BatchService 扩展

```python
class BatchService:
    _output_directory_override: OutputDirectoryRule | None = None

    def set_output_directory_override(self, rule: OutputDirectoryRule | None) -> None:
        """DesktopApi 切换项目时调用。None 表示回到默认（源文件旁）。"""

    def start(self, inputs: Sequence[Path], *, project_id: str | None = None) -> bool:
        """新增可选 project_id 参数。透传到 create_job。
        默认取 self._current_project_id（由 set_current_project 设置）。"""
```

- `create_job` 调用扩展为 `store.create_job(source, project_id=project_id)`
- `JobStore.create_job` 签名新增 `project_id: str | None = None`，写入 `jobs.project_id`
- 输出路径计算在 `_finish_item` 内根据 `_output_directory_override` 决定目录

### 7.3 监视文件夹绑定

`WatchFolderService.enqueue_from_watch` 入队时，若该 watch folder 绑定了 `project_id`，
则用该 `project_id` 覆盖 `BatchService._current_project_id` 传给 `start`：

```python
def enqueue_from_watch(self, paths: Sequence[Path]) -> int:
    # 取出 watch folder 的 project_id（按 path 查 settings）
    folder_project_id = self._resolve_folder_project(paths)
    self._service.start(paths, project_id=folder_project_id or self._current_project_id)
```

> 监视文件夹绑定的项目优先级高于全局 `current_project_id`，符合"不同客户文件夹
> 自动归属不同项目"的预期。

### 7.4 bootstrap 返回字段扩展

`bootstrap()` 返回字段新增：

```python
"projects": self._list_project_summaries(),       # 列表（不含 preset 详情）
"current_project_id": self._settings.current_project_id,
```

---

## 8. 前端 UI 设计

### 8.1 批处理页顶部"当前项目"选择器

批处理工作区命令栏左侧新增项目选择器（位于现有"开始/暂停/取消"按钮之前）：

```
┌──────────────────────────────────────────────────────────┐
│ [▼ 客户A-商拍            ]  [开始] [暂停] [取消]  [3/3] │
└──────────────────────────────────────────────────────────┘
```

- 下拉首项为"无项目"，其后按 `last_used_at DESC` 列出项目
- 末项分隔线后是"管理项目…"入口，打开项目管理对话框
- 切换触发 `set_current_project`，套用成功后 toast 提示
- 选择器宽度自适应，长项目名省略号截断，hover 显示完整名称

### 8.2 项目管理对话框（CRUD）

复用 `app/web/components/dialog.js` 模式，新建 `app/web/projects/project-dialog.js`：

```
项目管理
──────────────────────────────────────────────────────────
┌────────────────────────────────────────────────────────┐
│ 客户A-商拍        最后使用：2026-07-29    [编辑] [删除]│
│ 客户B-婚车跟拍    最后使用：2026-07-28    [编辑] [删除]│
│ 工作室内拍        从未使用                [编辑] [删除]│
└────────────────────────────────────────────────────────┘
                                  [+ 新建] [导入…] [导出…]
```

**新建 / 编辑表单**（同一对话框，标题切换）：

| 字段 | 控件 | 说明 |
|---|---|---|
| 项目名称 | 文本输入 | 必填，重名软提示 |
| 处理预设 | 单选（fast / balanced / strict） | 复用设置页控件 |
| 边缘扩展 | 滑块（-30% ~ +100%） | 复用设置页控件 |
| 输出目录 | 三选一 + 子字段 | beside_source / project_subfolder（子文件夹名）/ fixed_directory（目录选择按钮） |
| 后处理配置 | 折叠区，内嵌子 spec 2 的后处理表单 | naming_template + watermark + exif |

- "删除"二次确认，提示"历史记录会保留，但不再显示项目归属"
- "导出"对选中项目调用 `export_preset`，触发浏览器下载 `.json`
- "导入"接受用户选择的 `.json`，调 `import_preset`，`new_name` 默认取文件内 name

### 8.3 前端模块结构

延续总纲 §3.3（无框架、无 CDN、CSP `connect-src 'none'`）：

```
app/web/projects/
  project-picker.js    选择器组件（挂载到批处理命令栏）
  project-dialog.js    CRUD + 导入导出对话框
app/web/batch/
  workspace.js         扩展：挂载点 + 切换后刷新参数 UI
app/web/core/
  state.js             扩展：projects / currentProjectId 状态切片
```

### 8.4 前端事件处理

| 事件 | 处理 |
|---|---|
| `project_changed` | 刷新选择器高亮、刷新设置页参数显示（反映已套用的项目参数） |
| `project_deleted` | 若删的是当前项目，选择器回退到"无项目"并 toast 提示 |

---

## 9. 测试边界

### 9.1 Python 单元测试（`tests/unit/`）

- `test_project_store.py`：
  - `ProjectPreset` 校验各分支（名称空 / preset 非法 / margin 越界 / post_process_config 非 Mapping）
  - `OutputDirectoryRule` 校验（mode 非法 / fixed_directory 缺失）
  - CRUD：create → get → update → delete 全流程
  - `ON DELETE SET NULL`：删项目后关联 job 的 `project_id` 变 NULL
  - 导出 / 导入往返一致性（导出 → 导入 → 字段相等）
  - 导入非法 JSON 抛 `ValueError`
- `test_job_store_v7.py`：
  - schema v6 → v7 迁移（建表 + 加列 + 索引）
  - `create_job(project_id=...)` 写入与读取
  - 旧库（无 project_id 列）迁移后旧 job 的 `project_id` 为 NULL
- `test_settings_projects.py`：
  - `current_project_id` 序列化 / 反序列化
  - `WatchFolder.project_id` 兼容旧 settings（缺失为 None）
- `test_desktop_projects.py`：
  - `set_current_project` 套用各参数的调用链（mock set_preset 等）
  - 切到 None 不回滚参数
  - 运行中批次切换项目的软提示路径

### 9.2 前端测试（`tests/frontend/*.test.cjs`）

- `project-picker.test.cjs`：
  - 选择器渲染（含"无项目" + 项目列表 + "管理项目…"）
  - 切换触发 bridge 调用
- `project-dialog.test.cjs`：
  - 列表渲染 + 删除二次确认
  - 新建 / 编辑表单校验
  - 导入 / 导出按钮调用对应 bridge 方法

### 9.3 集成测试（`tests/integration/`）

- `test_project_apply_e2e.py`（`@pytest.mark.slow`）：
  - 创建项目 A（strict + margin 50% + 后处理命名 `{client}_{seq:03}`）→
    切换到 A → 处理一批照片 → 验证输出文件名、目录、EXIF 符合 A 的预设
  - 切换到项目 B（fast + margin 0% + beside_source）→ 下一张起参数生效
  - 删除项目 A → 历史 job 仍在，`project_id` 变 NULL，历史列表"项目"列为空
  - 监视文件夹绑定 project_id → 入队任务自动归属该项目

### 9.4 视觉证据

- `docs/audits/v0.3.0/project-picker.png`：批处理页项目选择器
- `docs/audits/v0.3.0/project-dialog.png`：项目管理对话框
- `docs/audits/v0.3.0/project-form.png`：新建 / 编辑表单

---

## 10. 性能预算

| 指标 | 预算 | 测量方式 |
|---|---|---|
| `list_projects` 查询 | ≤ 20ms（100 个项目） | 单元测试计时 |
| `set_current_project` 套用 | ≤ 100ms（不含批次重载） | 单元测试计时 |
| 切换项目对推理基线影响 | 0（只改参数，不改推理路径） | 不引入推理改动 |
| 现有 P50 2.38s 推理基线 | 不变 | 集成测试对照 |

---

## 11. 隐私与离线约束

- **项目 / 客户名称视为敏感信息**：诊断包只统计 `projects` 表的记录数量
  （如 `"projects_count": 3`），**不导出名称、不导出 preset_json、不导出
  `current_project_id`**
- `output_directory_rule.fixed_directory` 可能含客户名，按现有路径保护规则
  不写入诊断包（延续 `docs/privacy.md` 的路径保护与子 spec 1 的监视文件夹路径保护）
- `post_process_config` 中的 EXIF Artist / Copyright / 水印文字可能含客户名，
  诊断包不导出（延续子 spec 2 §7 的客户名保护）
- 导入 / 导出的 `.json` 文件由用户显式选择路径，不写入诊断包、不进入日志
- 全部新功能不引入任何网络请求

---

## 12. 风险与未决项

### 12.1 风险

| 风险 | 缓解措施 |
|---|---|
| 切换项目时批次运行中，参数套用被拒 | 不阻塞切换；下一张起通过 `replace_processor_factory` 重试路径生效；UI 软提示 |
| `fixed_directory` 路径不可写 | `_finish_item` 写出前 `mkdir(parents=True, exist_ok=True)`，失败降级到源文件旁并 toast |
| 监视文件夹绑定的项目被删 | `enqueue_from_watch` 时 `project_id` 解析为 None（项目不存在），回退到全局 `current_project_id` |
| 导入的 `.json` 与当前 schema 不匹配 | 反序列化 fail-fast，`ValueError` 转 toast，不写入库 |
| schema v7 迁移失败 | 迁移前备份 `jobs.sqlite3.bak-v6`，失败回滚（沿用现有机制） |
| 两个连接（JobStore + ProjectStore）写 contention | WAL 模式支持；ProjectStore 写频率极低（仅切换 / CRUD）， contention 可忽略 |

### 12.2 已决策的开放问题

1. **是否提供"默认项目"概念（不选项目也套用某套预设）？**
   - 决策：**不提供**。"无项目"状态沿用全局 `settings.json`，保持向后兼容。
   - 依据：用户决策（2026-07-29）

2. **删除项目时是否软删除（保留可恢复）？**
   - 决策：**硬删除 + `ON DELETE SET NULL`**。历史 job 保留，项目记录移除。
   - 依据：用户决策（2026-07-29），符合"历史必须保留，项目可重建"

3. **切换项目是否立即重写当前批次的输出目录？**
   - 决策：**不重写已完成的**。`set_output_directory_override` 只影响后续写出；
     已完成的输出路径不变。
   - 依据：避免半路改目录导致批次内输出位置不一致

4. **监视文件夹是否必须绑定项目？**
   - 决策：**可选**。`project_id` 可空，未绑定时用全局 `current_project_id`。
   - 依据：兑现子 spec 1 决策 8，不强加耦合

---

## 13. 后续步骤

本子 spec 经用户 review 通过后：

1. 修正 / 确认第 12.2 节的开放问题
2. 交接到 writing-plans 制定实现计划
3. 按计划实现 schema v7 → ProjectStore → DesktopApi 桥接 → 前端选择器与对话框
4. 测试 → 视觉证据
5. 完成后进入子 spec 4（历史搜索与前后对比），其"按项目分组"依赖本 spec 的
   `jobs.project_id` 与 `projects` 表
