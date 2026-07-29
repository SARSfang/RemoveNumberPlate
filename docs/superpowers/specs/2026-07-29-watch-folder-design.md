# 子 Spec 1：监视文件夹（Watch Folder）设计

> 日期：2026-07-29
> 状态：待评审
> 所属总纲：[2026-07-29-v0.3.0-master-design.md](./2026-07-29-v0.3.0-master-design.md)
> 推进顺序：第 1 项（共 7 项）

---

## 1. 版本与范围

本子 spec 实现 v0.3.0 总纲中的"监视文件夹"功能。摄影师可在设置页登记多个待监视文件夹；工具在后台持续监听这些文件夹及其子目录，自动把新增或修改的照片入队处理。

**在范围内**：

- 设置页"监视文件夹"管理区块（增 / 删 / 启停 / 状态查看）
- `WatchFolderService` 后端服务（基于 `ReadDirectoryChangesW`，不轮询）
- `BatchService` 队列扩展（支持监视入队与自动续批）
- `JobStore` schema v5 迁移（新增 `file_mtime` / `file_size` 用于去重）
- `UserSettings` 扩展（`watch_folders` 字段）
- 前端监视状态可见性（空状态变面板 + 命令栏脉冲徽章）
- 应用启动时扫描已有未处理照片

**不在范围内**：

- 监视文件夹绑定独立预设（留给子 spec 3）
- 监视文件夹与项目/客户关联（留给子 spec 3）
- 拖入文件夹时勾选"开启监视"（明确不做，仅设置页入口）

---

## 2. 已确认需求决策

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 自动化程度 | 智能自动处理：批次未运行时自动 start；批次运行中则等当前批次结束后自动续上下一批 |
| 2 | 开启入口 | 仅设置页（拖入时不变） |
| 3 | 监视范围 | 递归子目录（与现有 `discover_images` 递归展开一致） |
| 4 | 持续模式 | 持续监视直到手动关闭 |
| 5 | 启动扫描 | 应用启动时扫描监视文件夹中所有未处理照片并自动入队；扫描可被用户取消 |
| 6 | 重复入队 | 已 completed 跳过；文件被修改（mtime + size 变化）则重处理 |
| 7 | UI 可见性 | A + B 结合：空状态变"监视中"面板 + 命令栏脉冲徽章 |
| 8 | 预设绑定 | 先用全局设置处理，子 spec 3 实现后再加 `preset_id` |
| 9 | cancel 与队列 | cancel 当前批次时清空 `_watch_queue`（明确的"放弃"语义） |
| 10 | start 空参数 | `start` 不接受空 paths；cancel 后用户手动"开始"需要显式选择文件或等监视续批 |
| 11 | 网络驱动器 | 不支持；运行时检测路径类型，网络路径拒绝启用并提示用户 |
| 12 | 启动扫描取消 | 启动扫描异步执行，用户可在 UI 取消；取消后已入队的照片保留 |

---

## 3. 架构概览

### 3.1 实现方案

采用**方案 1：WatchFolderService + BatchService 队列扩展**。

```
┌─ app/desktop.py ─────────────────────────────────────────────┐
│  DesktopApi                                                  │
│    ├─ BatchService (扩展)                                    │
│    │    新增 enqueue_from_watch(paths) → 加入 _watch_queue   │
│    │    _run 结尾检查 _watch_queue → 自动续批                │
│    │                                                         │
│    └─ WatchFolderService (新)                                │
│         start() / stop() / add_folder(path) / remove(...)   │
│         独立守护线程，ReadDirectoryChangesW 监听             │
│         文件稳定检测 (mtime 间隔 ≥1.5s)                     │
│         去重: 查 JobStore 同路径记录, 比较 mtime+size        │
│         入队: 调 BatchService.enqueue_from_watch(paths)      │
└─────────────────────────────────────────────────────────────┘

┌─ app/core/ ──────────────────────────────────────────────────┐
│  job_store.py (扩展)                                        │
│    新增 find_recent_by_source(path) → 用于去重比较           │
│  settings.py (扩展)                                         │
│    UserSettings 新增 watch_folders: list[WatchFolder]       │
│  watch_folder.py (新)                                       │
│    WatchFolder dataclass + WatchFolderService               │
└─────────────────────────────────────────────────────────────┘

┌─ app/web/ ──────────────────────────────────────────────────┐
│  settings/settings.js (扩展)                                │
│    新增"监视文件夹"管理区块                                 │
│  batch/workspace.js (扩展)                                  │
│    空状态: drop-zone 变"监视中"面板 (方案 A)                │
│    运行中: 命令栏脉冲徽章 (方案 B)                          │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 组件职责与依赖方向

- `WatchFolderService`：只负责"发现 + 稳定检测 + 去重 + 入队"，不处理图片
- `BatchService`：只负责"处理 + 事件推送"，新增队列入口和续批检查
- `JobStore`：提供去重查询接口
- 前端：只负责状态展示和设置管理

**关键设计原则**：WatchFolderService 不知道"怎么处理"，BatchService 不知道"照片从哪来"——单向依赖。

### 3.3 方案对比（已评估）

| 方案 | 描述 | 评价 |
|---|---|---|
| **方案 1（采纳）** | WatchFolderService + BatchService 队列扩展 | 复用现有处理流程；架构清晰；前端无需大改 |
| 方案 2 | 外部 WatchBatchRunner 调度 | 不碰 BatchService 核心，但两个管理者竞态风险高 |
| 方案 3 | WatchFolderService 内嵌完整批处理 | 重复实现，与手动批处理体验割裂 |

---

## 4. WatchFolderService 详细设计

### 4.1 类接口

```python
class WatchFolderService:
    def __init__(self, job_store: JobStore, event_sink: EventSink): ...

    # 生命周期
    def start(self) -> None: ...           # 启动所有 enabled 的监视器
    def stop(self) -> None: ...            # 停止所有监视器（应用退出时调用）

    # 文件夹管理（设置页调用）
    def add_folder(self, path: Path) -> WatchFolder: ...
    def remove_folder(self, path: Path) -> None: ...
    def set_enabled(self, path: Path, enabled: bool) -> None: ...
    def list_folders(self) -> list[WatchFolder]: ...

    # BatchService 调用（启动/退出时）
    def rescan_existing(self) -> list[Path]: ...  # 扫描已有未处理文件

    # 回调注入
    def set_enqueue_callback(self, cb: Callable[[list[Path]], None]) -> None: ...
```

### 4.2 守护线程模型

每个被监视文件夹一个 `ReadDirectoryChangesW` 线程，通过 `Queue` 把事件投递给单个聚合线程：

```
[Folder A Watcher Thread] ─┐
                            ├─→ [Queue] → [Aggregator Thread] → enqueue_callback
[Folder B Watcher Thread] ─┘
```

- **Watcher Thread**：阻塞式 `ReadDirectoryChangesW`，捕获 `FILE_ACTION_ADDED` / `FILE_ACTION_MODIFIED`，把 `(path, action)` 推入 Queue
- **Aggregator Thread**：单线程消费 Queue，做"稳定检测 + 去重 + 入队"

### 4.3 文件稳定检测

摄影师的相机/读卡器拷贝过程中文件可能多次写入。采用 mtime 间隔策略：

```python
def _is_file_stable(path: Path) -> bool:
    stat = path.stat()
    now = time.time()
    return (now - stat.st_mtime) >= STABILITY_THRESHOLD  # 1.5 秒
```

- 收到 `ADDED` / `MODIFIED` 事件 → 加入 `_pending` 字典（path → 最后事件时间）
- 每秒扫描 `_pending`，稳定的文件移出，走去重检查
- 不稳定的继续等

### 4.4 去重策略

```python
def _should_enqueue(path: Path) -> bool:
    # 1. 扩展名白名单（沿用 discover_images）
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return False

    # 2. 查 JobStore 是否已存在
    existing = job_store.find_recent_by_source(str(path))
    if existing is None:
        return True  # 从未处理过

    # 3. 已完成且文件未变化 → 跳过
    if existing.status == JobStatus.COMPLETED:
        if (existing.file_mtime == path.stat().st_mtime and
            existing.file_size == path.stat().st_size):
            return False  # 已处理且文件未变

    # 4. 已完成但文件已变化 → 重处理
    # 5. 队列中/处理中 → 跳过（避免重复入队）
    if existing.status in (JobStatus.QUEUED, JobStatus.DETECTING,
                          JobStatus.INPAINTING, JobStatus.WRITING):
        return False

    return True
```

### 4.5 错误恢复

| 故障 | 处理 |
|---|---|
| 文件夹被删除 | Watcher 线程捕获错误，emit `watch_folder_error` 事件，自动 `set_enabled(path, False)` |
| 文件夹被移动/重命名 | 同上 |
| Watcher 线程崩溃 | Aggregator 检测到 watcher 退出，emit 事件，标记该文件夹为 disabled |
| 应用启动时文件夹不存在 | 启动扫描跳过该文件夹，emit `watch_folder_error`，保持 enabled 状态（下次启动再尝试） |
| 网络驱动器路径 | `add_folder` 时检测路径类型，网络路径拒绝启用并提示"不支持网络驱动器" |

### 4.6 网络驱动器检测

```python
def _is_network_path(path: Path) -> bool:
    """检测是否为网络驱动器（UNC 路径或映射网络盘）"""
    path_str = str(path.resolve())
    # UNC 路径（如 \\server\share）
    if path_str.startswith("\\\\"):
        return True
    # 检查驱动器类型（GetDriveType）
    import ctypes
    drive = ctypes.windll.kernel32.GetDriveTypeW(f"{path_str[:3]}")
    # DRIVE_REMOTE = 4
    return drive == 4
```

- `add_folder` 调用时立即检测；网络路径返回错误，不写入 settings
- `start()` 启动扫描时再次检测（防止用户通过编辑 settings.json 绕过）

### 4.7 启动扫描取消

启动扫描异步执行，支持取消：

```python
def rescan_existing(self, cancel_event: threading.Event) -> list[Path]:
    """扫描已有未处理文件。cancel_event 被设置时立即返回已收集的路径。"""
    collected = []
    for folder in self._enabled_folders():
        if cancel_event.is_set():
            break
        for path in discover_images([Path(folder.path)]):
            if cancel_event.is_set():
                break
            if self._should_enqueue(path):
                collected.append(path)
    return collected
```

- `DesktopApi` 在 `bootstrap()` 前启动异步扫描线程
- `bootstrap()` 返回字段新增 `watch_scan_in_progress: True`
- 扫描完成后 emit `watch_scan_complete` 事件，含 `collected_count`
- 前端可显示"启动扫描中..."状态，并提供取消按钮
- 取消后已收集的路径仍会入队（符合"取消后已入队的照片保留"）

---

## 5. BatchService 队列扩展

### 5.1 新增字段

```python
class BatchService:
    _watch_queue: list[Path]           # 等待续批的监视入队照片
    _watch_pending: set[str]           # 已入队但未处理的 source（避免重复 enqueue）
    _watch_lock: threading.Lock        # 保护 _watch_queue / _watch_pending
```

### 5.2 新增方法

```python
def enqueue_from_watch(self, paths: Sequence[Path]) -> int:
    """WatchFolderService 调用。返回实际入队数量。

    - 若当前无批次（_busy=False）且 _watch_queue 空：直接 start(paths)
    - 若当前有批次或队列非空：加入 _watch_queue，等当前批次结束后续批
    - 去重：_watch_pending 已存在的 source 跳过
    """
```

### 5.3 _run 结尾续批逻辑

在现有 `_run` 方法最后（`_finish(False)` 之前）插入检查：

```python
# 现有循环结束
self._finish(False)

# 新增：检查监视队列
if not self._cancelled:
    with self._watch_lock:
        pending = list(self._watch_queue)
        self._watch_queue.clear()
        # 清理 _watch_pending 中已处理的 source
        for p in pending:
            self._watch_pending.discard(str(p))

    if pending:
        # 自动续批：递归调 start
        self.start(pending)
```

### 5.4 事件流

监视入队的照片走正常 `batch_*` 事件流，前端无需区分"手动批次"和"监视批次"：

```
WatchFolderService → enqueue_from_watch(paths)
  ├─ 无批次时: start(paths) → batch_accepted → ... → batch_finished
  └─ 有批次时: 入 _watch_queue
                  ↓ 当前批次 batch_finished
                  ↓ _run 结尾检查 _watch_queue
                  ↓ 自动 start(pending) → 新一轮 batch_accepted → ...
```

### 5.5 pause / cancel 与监视队列的交互

| 用户操作 | 对 _watch_queue 的影响 |
|---|---|
| pause 当前批次 | `_watch_queue` 不变，续批逻辑在 resume 后才触发 |
| cancel 当前批次 | `_run` 走 `_finish(True)`，跳过续批检查；**`_watch_queue` 清空**（明确的"放弃"语义）；`_watch_pending` 也清空 |
| 关闭应用 | `stop()` 时清理 `_watch_queue`，已入队但未处理的丢失（符合"完全离线"语义） |

**cancel 语义**：cancel 是用户明确的"我不要了"信号——既取消当前批次，也清空监视队列。用户若想重新处理，需手动选择文件或等监视服务后续检测到新文件。

### 5.6 start 方法不变

`start` 方法签名与行为完全不变：

```python
def start(self, inputs: Sequence[Path]) -> bool:
    with self._condition:
        if self._busy:
            return False
        if not inputs:
            return False  # 不接受空参数
        # ... 现有逻辑
```

- 前端 `start_batch` 调用不变（传 paths）
- 监视续批时 `start(pending)` 直接调（pending 非空）
- cancel 后用户手动"开始"必须显式选择文件

### 5.7 关键不变量

- **`_busy` 仍然只表示"当前批次运行中"**，不变
- **手动批次的 `start` 行为完全不变**：仍被 `_busy` 拒绝，不接受空参数，仍走原流程
- **监视批次与手动批次互斥**：不会同时运行两个批次
- **cancel 清空所有监视队列状态**：`_watch_queue` 和 `_watch_pending` 都清空

---

## 6. 数据模型变更

### 6.1 settings.json schema

新增 `watch_folders` 字段：

```json
{
  "preset": "balanced",
  "mask_margin_ratio": 0.35,
  "watch_folders": [
    {
      "path": "D:/商拍/2026-07-客户A",
      "enabled": true,
      "added_at": "2026-07-29T10:30:00Z"
    },
    {
      "path": "E:/摄影/婚车跟拍",
      "enabled": false,
      "added_at": "2026-07-29T11:00:00Z"
    }
  ]
}
```

- `path`：绝对路径字符串
- `enabled`：是否启用监视
- `added_at`：登记时间（ISO 8601 UTC），用于设置页排序
- **不包含 `preset_id`**：按需求决策 8，先用全局设置，子 spec 3 实现后扩展

### 6.2 jobs.sqlite3 schema v5 迁移

新增字段（用于去重比较）：

```sql
ALTER TABLE jobs ADD COLUMN file_mtime REAL;
ALTER TABLE jobs ADD COLUMN file_size INTEGER;
```

- 在 `create_job` 时填入
- 用于去重比较，不暴露给前端

### 6.3 JobStore 新增方法

```python
def get_latest_by_source(self, source: str) -> StoredJob | None:
    """返回指定 source 路径最近一条 job 记录，无则 None。
    按 created_at DESC 排序，取第一条。
    """
```

> 命名沿用现有 `get_job` 模式，不引入 `find_by_*` 新风格。

### 6.4 UserSettings dataclass 扩展

```python
@dataclass(frozen=True)
class WatchFolder:
    path: str
    enabled: bool
    added_at: str  # ISO 8601 UTC

@dataclass(frozen=True)
class UserSettings:
    preset: str = "balanced"
    mask_margin_ratio: float = DEFAULT_MARGIN_RATIO
    watch_folders: tuple[WatchFolder, ...] = ()  # 不可变，新值用 replace
```

> `SettingsStore` 的序列化沿用现有内联模式（`load_with_recovery` / `save` 内部直接处理 JSON），不引入 `to_dict` / `from_dict`。

### 6.5 迁移与兼容性

- 旧 `settings.json` 无 `watch_folders` 字段 → 反序列化时默认空 tuple
- 旧 `jobs.sqlite3` schema v4 → 自动迁移到 v5，`file_mtime` / `file_size` 填 NULL
- 旧 job 记录的 `file_mtime` 为 NULL 时，去重逻辑降级为"已 completed 即跳过，不比较 mtime"

---

## 7. 前端 UI 设计

### 7.1 方案 A：空状态变"监视中"面板

当 `watch_folders` 中有 enabled 项且无批处理运行时，`#drop-zone` 区域变为监视状态面板：

```
┌─────────────────────────────────────┐
│           [雷达图标]                │
│            监视中                   │
│      正在监视 2 个文件夹            │
│                                     │
│    已捕获 5 张    已处理 3 张       │
└─────────────────────────────────────┘
```

- 替换 `#drop-zone` 内容，保留拖放功能（用户仍可拖入新照片手动入批）
- 数据来源：后端推送的 `watch_status` 事件

### 7.2 方案 B：命令栏脉冲徽章

当 `watch_folders` 中有 enabled 项时，命令栏右侧新增脉冲徽章：

```
[批处理 3/3 完成]          [● 监视中 (2)]
```

- 始终可见（运行中、空状态都显示）
- 脉冲点遵守 `prefers-reduced-motion`
- 点击徽章跳转到设置页监视文件夹区块

### 7.3 设置页"监视文件夹"管理区块

在设置页现有 3 个区块之间新增第 4 个区块（位置：处理 / 性能 / **监视文件夹** / 数据与支持）：

```
02 · 监视文件夹
─────────────────────────────────────────────
┌─────────────────────────────────────────┐
│ ✓ D:/商拍/2026-07-客户A    [暂停] [移除]│
│ ○ E:/摄影/婚车跟拍         [启用] [移除]│
└─────────────────────────────────────────┘
              [+ 添加监视文件夹]
```

- 每行一个监视文件夹：路径 + 启停按钮 + 移除按钮
- "添加"按钮调用 `choose_folder` 选目录
- 路径显示截断长路径，hover 显示完整路径
- 启停即时生效（调用 `set_enabled`）
- 移除需二次确认

### 7.4 DesktopApi 桥接方法

新增白名单 API（延续不接收任意路径、只传 ID/配置对象的原则）：

```python
# 监视文件夹管理
def list_watch_folders(self) -> list[dict]: ...
def add_watch_folder(self) -> dict | None: ...  # 弹文件夹选择对话框
def remove_watch_folder(self, path: str) -> None: ...
def set_watch_folder_enabled(self, path: str, enabled: bool) -> None: ...
```

- 路径通过 `path` 字符串传递，但仅限已登记到 `settings.json` 的路径（`add_watch_folder` 通过系统对话框获取，不接受前端任意传入）

### 7.5 前端事件处理

新增事件类型：

| 事件 | 处理 |
|---|---|
| `watch_status` | 更新空状态面板与命令栏徽章的数字 |
| `watch_folder_error` | toast 提示 + 自动禁用对应文件夹 UI |
| `watch_file_detected` | 空状态面板"已捕获"计数 +1 |

---

## 8. 事件清单汇总

### 8.1 WatchFolderService 发出

| 事件名 | 时机 | payload |
|---|---|---|
| `watch_started` | 监视启动 | `{folder: str}` |
| `watch_stopped` | 监视停止（手动关闭/错误） | `{folder: str, reason: "manual"\|"error"\|"removed"}` |
| `watch_file_detected` | 文件入队前 | `{folder: str, file: str, total_pending: int}` |
| `watch_folder_error` | 文件夹异常 | `{folder: str, error: str}` |
| `watch_status` | 周期性（每 5 秒）或状态变化时 | `{active_count: int, captured: int, processed: int}` |
| `watch_scan_started` | 启动扫描开始 | `{}` |
| `watch_scan_progress` | 启动扫描进度 | `{scanned: int, collected: int}` |
| `watch_scan_complete` | 启动扫描完成 | `{collected_count: int, cancelled: bool}` |

### 8.2 BatchService 行为不变

- 所有现有 `batch_*` 事件流不变
- 监视入队的照片走正常事件流，前端无需区分来源

---

## 9. 应用启动流程

```
DesktopApi.__init__
  → 加载 UserSettings（含 watch_folders）
  → 创建 JobStore
  → 创建 BatchService
  → 创建 WatchFolderService(job_store, event_sink)
  → WatchFolderService.set_enqueue_callback(BatchService.enqueue_from_watch)
  → WatchFolderService.start()
       ├─ 启动 Aggregator 线程
       └─ 对每个 enabled 文件夹启动 Watcher 线程（跳过网络驱动器）
  → 启动异步扫描线程：
       cancel_event = threading.Event()
       pending = WatchFolderService.rescan_existing(cancel_event)
       if pending: BatchService.enqueue_from_watch(pending)
       emit watch_scan_complete
  → bootstrap() 返回 watch_scan_in_progress: scan_thread.is_alive()
```

### 9.1 rescan_existing 行为

- 遍历所有 enabled 监视文件夹（递归）
- 跳过网络驱动器路径
- 对每个图片文件调用 `_should_enqueue`（与运行时去重逻辑一致）
- `cancel_event` 被设置时立即返回已收集的路径
- 由 `DesktopApi` 在启动序列中异步调用

### 9.2 应用退出流程

```
DesktopApi.shutdown
  → WatchFolderService.stop()
       ├─ 停止所有 Watcher 线程
       └─ 停止 Aggregator 线程
  → BatchService.wait(timeout=5.0)（等待当前任务完成或超时）
  → JobStore.close()
```

- `DesktopApi` 新增 `shutdown()` 方法（现有代码无退出钩子）
- 在 `launch()` 中注册窗口关闭事件回调
- 已入队但未处理的 `_watch_queue` 丢失（符合"完全离线"语义）
- 下次启动时由 `rescan_existing` 重新发现

---

## 10. 测试策略

### 10.1 Python 单元测试（`tests/unit/`）

- `test_watch_folder_service.py`：
  - 模拟 `ReadDirectoryChangesW` 事件（mock win32 API）
  - 文件稳定检测（mtime 阈值）
  - 去重策略各分支
  - 错误恢复（文件夹被删除/移动）
- `test_batch_service_watch_queue.py`：
  - `enqueue_from_watch` 在无批次/有批次时的行为
  - `_run` 结尾续批逻辑
  - cancel 保留队列、pause 不影响队列
- `test_job_store_v5.py`：
  - schema 迁移
  - `find_recent_by_source` 查询
- `test_settings_watch_folders.py`：
  - 序列化/反序列化
  - 旧 settings 兼容

### 10.2 前端测试（`tests/frontend/*.test.cjs`）

- `settings-watch-folders.test.cjs`：
  - 列表渲染
  - 启停按钮交互
  - 移除二次确认
- `batch-watch-indicator.test.cjs`：
  - 命令栏徽章显示/隐藏
  - 空状态面板切换

### 10.3 集成测试（`tests/integration/`）

- `test_watch_folder_e2e.py`（`@pytest.mark.slow`）：
  - 真实文件夹 + 真实文件创建 → 自动入队 → 处理完成
  - 文件修改 → 重处理
  - 文件夹删除 → 错误事件 + 自动禁用
  - 应用"重启"（重新初始化服务）→ rescan_existing 正确恢复

### 10.4 视觉证据

- `docs/audits/v0.3.0/watch-folder-settings.png`：设置页管理区块
- `docs/audits/v0.3.0/watch-folder-empty-panel.png`：空状态监视面板
- `docs/audits/v0.3.0/watch-folder-commandbar-badge.png`：命令栏脉冲徽章

---

## 11. 性能预算

| 指标 | 预算 | 测量方式 |
|---|---|---|
| 新增照片入队延迟 | ≤ 2 秒（从文件稳定到 `enqueue_from_watch` 调用） | 集成测试计时 |
| 监视线程空闲 CPU | ≤ 1%（单文件夹） | 任务管理器观察 |
| 启动扫描耗时（500 文件） | ≤ 3 秒 | 集成测试计时 |
| 现有 P50 2.38s 推理基线 | 不变 | 不引入处理路径改动 |

---

## 12. 隐私与离线约束

- 监视文件夹路径不写入诊断包（延续 `docs/privacy.md` 的路径保护）
- 诊断包只统计 `watch_folders` 数量，不导出路径
- 全部新功能不引入任何网络请求
- 监视状态事件（`watch_status`）只含计数，不含路径

---

## 13. 风险与未决项

### 13.1 风险

| 风险 | 缓解措施 |
|---|---|
| `ReadDirectoryChangesW` 在网络驱动器上的稳定性 | 文档提示仅支持本地磁盘；运行时检测路径类型，网络路径拒绝启用 |
| 大量文件同时入队导致 BatchService 长时间占用 | 现有串行处理已天然限流；续批机制保证不阻塞 UI |
| Watcher 线程在系统休眠/唤醒后失效 | Aggregator 检测 watcher 退出后 emit 错误；用户可在设置页重新启用 |
| schema v5 迁移失败 | 沿用现有备份机制：迁移前备份 `jobs.sqlite3.bak-v4`，失败回滚 |
| 1.5 秒稳定阈值对大文件（如 50MB RAW）过短 | 摄影师主要用 JPEG/TIFF（已支持格式），单文件 < 20MB；RAW 留给 v0.4 |

### 13.2 已决策的开放问题

1. **cancel 后是否保留 `_watch_queue`？**
   - 决策：**不保留**。cancel 清空 `_watch_queue` 和 `_watch_pending`，明确的"放弃"语义。
   - 依据：用户决策（2026-07-29）

2. **`start` 方法"传空 paths 也能触发消费队列"是否可接受？**
   - 决策：**不可接受**。`start` 不接受空参数，行为完全不变。
   - 依据：用户决策（2026-07-29）

3. **网络驱动器是否支持？**
   - 决策：**不支持**。`add_folder` 时检测路径类型，网络路径拒绝启用并提示。
   - 依据：用户决策（2026-07-29）

4. **启动扫描是否可被用户取消？**
   - 决策：**可取消**。异步扫描，用户可在 UI 取消；取消后已收集的路径仍入队。
   - 依据：用户决策（2026-07-29）

---

## 14. 后续步骤

本子 spec 经用户 review 通过后：

1. 修正/确认第 13.2 节的开放问题
2. 交接到 writing-plans 制定实现计划
3. 按计划实现 → 测试 → 视觉证据
4. 完成后进入子 spec 2（批量后处理）
