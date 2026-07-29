# 子 Spec 1 实现计划：监视文件夹

> 日期：2026-07-29
> 对应 spec：[2026-07-29-watch-folder-design.md](../specs/2026-07-29-watch-folder-design.md)
> 推进顺序：第 1 项（共 7 项）

---

## 计划概览

实现分 8 个阶段，按依赖顺序推进。每个阶段产出可独立验证的成果。

| 阶段 | 内容 | 依赖 | 验证 |
|---|---|---|---|
| 0 | Spec 修正与准备 | 无 | Spec 同步 |
| 1 | 数据层基础 | 0 | 单测通过 |
| 2 | WatchFolderService 核心 | 1 | 单测通过 |
| 3 | BatchService 队列扩展 | 1 | 单测通过 |
| 4 | DesktopApi 桥接 | 2, 3 | 单测通过 |
| 5 | 前端 UI | 4 | 前端测试通过 |
| 6 | 集成测试与视觉证据 | 5 | 集成测试通过 |
| 7 | 文档同步与回归 | 6 | 全量回归通过 |

---

## 阶段 0：Spec 修正与准备

### 任务 0.1：修正 spec 命名不一致

**文件**：`e:\消除车牌\docs\superpowers\specs\2026-07-29-watch-folder-design.md`

**改动**：
- 第 4.4、6.3 节：`find_recent_by_source` → `get_latest_by_source`（与现有 `get_job` 命名模式一致）
- 第 6.4 节：`JobRecord` → `StoredJob`（与现有 dataclass 命名一致）
- 第 5.6 节：补充说明 `SettingsStore` 序列化沿用内联模式，不引入 `to_dict`/`from_dict`
- 第 9 节：补充 `DesktopApi.shutdown()` 方法需新增（现有代码无退出钩子）

**验证**：spec 自审通过，无内部矛盾。

### 任务 0.2：创建实现分支（可选）

```bash
git checkout -b feat/watch-folder-v0.3.0
```

---

## 阶段 1：数据层基础

### 任务 1.1：JobStore schema v5 迁移

**文件**：[app/core/job_store.py](file:///e:/消除车牌/app/core/job_store.py)

**改动**：
1. 第 17 行：`SCHEMA_VERSION = 4` → `SCHEMA_VERSION = 5`
2. `StoredJob` dataclass（第 63-74 行）新增字段：
   ```python
   file_mtime: float | None = None
   file_size: int | None = None
   ```
3. `CREATE TABLE jobs` 语句新增两列（新建库时）
4. `_initialize()` 方法（第 89-174 行）新增 `current_version < 5` 分支：
   ```python
   if current_version < 5:
       self._conn.execute("ALTER TABLE jobs ADD COLUMN file_mtime REAL")
       self._conn.execute("ALTER TABLE jobs ADD COLUMN file_size INTEGER")
   ```
5. `create_job` 方法（第 191 行）改为接受可选 `file_mtime`/`file_size`，或内部 `source.stat()` 自动获取
6. `_stored_job_from_row`（第 320-372 行）读取新字段
7. `_row_from_stored_job`（若有反操作）写入新字段

**验证**：
- 现有测试 `test_job_store_migrates_v1_database_without_losing_jobs`（[tests/unit/test_job_store.py:106](file:///e:/消除车牌/tests/unit/test_job_store.py)）仍通过
- 新增测试 `test_job_store_migrates_v4_to_v5_with_file_metadata`：构造 v4 库 → 打开 → 验证 file_mtime/file_size 列存在且为 NULL

### 任务 1.2：新增去重查询方法

**文件**：[app/core/job_store.py](file:///e:/消除车牌/app/core/job_store.py)

**改动**：新增方法
```python
def get_latest_by_source(self, source: str) -> StoredJob | None:
    """返回指定 source 路径最近一条 job 记录，无则 None。
    按 created_at DESC 排序，取第一条。
    """
```

**验证**：
- 新增测试 `test_job_store_get_latest_by_source_returns_most_recent`
- 新增测试 `test_job_store_get_latest_by_source_returns_none_when_empty`

### 任务 1.3：UserSettings 扩展 watch_folders

**文件**：[app/settings.py](file:///e:/消除车牌/app/settings.py)

**改动**：
1. 新增 `WatchFolder` dataclass：
   ```python
   @dataclass(frozen=True, slots=True)
   class WatchFolder:
       path: str
       enabled: bool
       added_at: str  # ISO 8601 UTC
   ```
2. `UserSettings`（第 21-40 行）新增字段：
   ```python
   watch_folders: tuple[WatchFolder, ...] = ()
   ```
3. `__post_init__` 新增校验：路径非空字符串、added_at 格式合法
4. `SettingsStore.load_with_recovery`（第 50-74 行）反序列化：
   ```python
   watch_data = value.get("watch_folders", [])
   watch_folders = tuple(
       WatchFolder(
           path=item["path"],
           enabled=item.get("enabled", True),
           added_at=item["added_at"],
       ) for item in watch_data
   )
   ```
5. `SettingsStore.save`（第 76-90 行）序列化：
   ```python
   "watch_folders": [
       {"path": w.path, "enabled": w.enabled, "added_at": w.added_at}
       for w in settings.watch_folders
   ]
   ```

**验证**：
- 现有 `tests/unit/test_settings.py` 测试通过（旧 settings.json 无 watch_folders 字段 → 默认空 tuple）
- 新增测试 `test_settings_round_trips_watch_folders`
- 新增测试 `test_settings_loads_old_settings_without_watch_folders`

---

## 阶段 2：WatchFolderService 核心

### 任务 2.1：WatchFolderService 骨架

**文件**：新建 `e:\消除车牌\app\core\watch_folder.py`

**内容**：
- `WatchFolderService` 类骨架（所有方法 stub）
- `__init__(self, job_store: JobStore, event_sink: EventSink)`
- 字段：`_folders: dict[str, WatchFolderEntry]`、`_watchers: dict[str, threading.Thread]`、`_aggregator_thread`、`_event_queue: queue.Queue`、`_running: threading.Event`、`_enqueue_callback: Callable | None`
- `WatchFolderEntry` 内部 dataclass：`watch_folder: WatchFolder`、`watcher_thread: threading.Thread | None`、`error: str | None`

**验证**：
- 文件可被 import，无语法错误
- 新增测试文件 `tests/unit/test_watch_folder_service.py`，测试 `list_folders()` 返回空列表

### 任务 2.2：Watcher 线程（ReadDirectoryChangesW）

**文件**：[app/core/watch_folder.py](file:///e:/消除车牌/app/core/watch_folder.py)

**内容**：
- `_watcher_loop(self, path: str)` 方法
- 使用 `win32file.ReadDirectoryChangesW`（或 `ctypes` 直接调用，避免 pywin32 依赖）
- 监听 `FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_SIZE`
- 捕获 `FILE_ACTION_ADDED` / `FILE_ACTION_MODIFIED` / `FILE_ACTION_RENAMED_NEW_NAME`
- 把 `(path, action, time.time())` 推入 `self._event_queue`
- 错误捕获：`OSError` / `winerror` → emit `watch_folder_error` + 标记 disabled

**依赖决策**：是否引入 `pywin32` 还是直接 `ctypes`？
- **推荐 ctypes**：避免新增运行时依赖，与现有"完全离线、不依赖外部库"原则一致
- 备选：`pywin32`（更稳定但增加打包体积）

**验证**：
- 单测 `test_watch_folder_watcher_detects_new_file`（mock ctypes 调用）
- 单测 `test_watch_folder_watcher_emits_error_on_missing_folder`

### 任务 2.3：Aggregator 线程 + 文件稳定检测

**文件**：[app/core/watch_folder.py](file:///e:/消除车牌/app/core/watch_folder.py)

**内容**：
- `_aggregator_loop(self)` 方法
- `_pending: dict[str, float]`（path → 最后事件时间）
- 每秒扫描 `_pending`，调用 `_is_file_stable(path)` 判断
- `_is_file_stable` 实现：`time.time() - stat.st_mtime >= 1.5`
- 稳定文件移出 `_pending`，调 `_should_enqueue` → `_enqueue_callback`

**验证**：
- 单测 `test_aggregator_waits_for_file_stability`（模拟文件 mtime < 1.5s → 不入队；> 1.5s → 入队）
- 单测 `test_aggregator_handles_disappearing_file`（pending 中文件被删除）

### 任务 2.4：去重策略

**文件**：[app/core/watch_folder.py](file:///e:/消除车牌/app/core/watch_folder.py)

**内容**：
- `_should_enqueue(self, path: Path) -> bool` 方法
- 实现 spec 第 4.4 节逻辑：
  1. 扩展名白名单检查（复用 `discover_images` 的 `IMAGE_EXTENSIONS`）
  2. 调 `job_store.get_latest_by_source(str(path))`
  3. None → True
  4. COMPLETED 且 mtime+size 未变 → False
  5. 队列中/处理中状态 → False
  6. 其他 → True

**验证**：
- 单测覆盖每个分支（6 个测试用例）

### 任务 2.5：错误恢复

**文件**：[app/core/watch_folder.py](file:///e:/消除车牌/app/core/watch_folder.py)

**内容**：
- watcher 线程异常捕获
- aggregator 检测 watcher 退出（`watcher.is_alive() == False`）
- emit `watch_folder_error` 事件
- 自动 `set_enabled(path, False)`
- 文件夹不存在时启动扫描跳过，保持 enabled 状态

**验证**：
- 单测 `test_watch_folder_service_disables_on_folder_deletion`
- 单测 `test_watch_folder_service_keeps_enabled_when_missing_at_startup`

### 任务 2.6：rescan_existing 实现（支持取消）

**文件**：[app/core/watch_folder.py](file:///e:/消除车牌/app/core/watch_folder.py)

**内容**：
- `rescan_existing(self, cancel_event: threading.Event) -> list[Path]` 方法
- 遍历所有 enabled 文件夹（跳过网络驱动器），递归（复用 `discover_images` 的递归逻辑）
- 对每个文件调 `_should_enqueue`
- `cancel_event.is_set()` 时立即返回已收集的路径
- 返回需要入队的路径列表

**验证**：
- 单测 `test_rescan_existing_finds_unprocessed_files`
- 单测 `test_rescan_existing_skips_completed_files`
- 单测 `test_rescan_existing_skips_network_drives`
- 单测 `test_rescan_existing_returns_partial_on_cancel`

### 任务 2.7：事件推送

**文件**：[app/core/watch_folder.py](file:///e:/消除车牌/app/core/watch_folder.py)

**内容**：
- `_emit(self, name: str, payload: dict)` 方法（转发给 `event_sink`）
- 实现 spec 第 8.1 节的 8 个事件（含启动扫描 3 个事件）
- `watch_status` 周期性推送（每 5 秒）或状态变化时
- 启动扫描期间 emit `watch_scan_started` / `watch_scan_progress` / `watch_scan_complete`

**验证**：
- 单测 `test_watch_folder_service_emits_status_periodically`
- 单测 `test_watch_folder_service_emits_scan_events`

### 任务 2.8：网络驱动器检测

**文件**：[app/core/watch_folder.py](file:///e:/消除车牌/app/core/watch_folder.py)

**内容**：
- `_is_network_path(path: Path) -> bool` 静态方法
- 检测 UNC 路径（`\\server\share`）和映射网络盘（`GetDriveTypeW` 返回 `DRIVE_REMOTE`）
- 使用 `ctypes.windll.kernel32.GetDriveTypeW`，不引入 pywin32 依赖
- `add_folder` 调用时检测；网络路径返回错误，不写入 settings
- `start()` 启动扫描时再次检测

**验证**：
- 单测 `test_is_network_path_detects_unc_path`
- 单测 `test_is_network_path_detects_mapped_drive`（mock GetDriveTypeW）
- 单测 `test_add_folder_rejects_network_path`

---

## 阶段 3：BatchService 队列扩展

### 任务 3.1：新增字段与初始化

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py) 第 83-98 行

**改动**：
- `__init__` 新增字段初始化：
  ```python
  self._watch_queue: list[Path] = []
  self._watch_pending: set[str] = set()
  self._watch_lock = threading.Lock()
  ```

**验证**：现有测试 `test_batch_service_rejects_controls_while_idle` 等仍通过。

### 任务 3.2：enqueue_from_watch 方法

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py)

**改动**：新增方法
```python
def enqueue_from_watch(self, paths: Sequence[Path]) -> int:
    """WatchFolderService 调用。返回实际入队数量。"""
    with self._watch_lock:
        new_paths = [p for p in paths if str(p) not in self._watch_pending]
        if not new_paths:
            return 0
        self._watch_pending.update(str(p) for p in new_paths)
    
    # 无批次且队列空 → 直接 start
    if not self._busy and not self._watch_queue:
        self.start(new_paths)
        return len(new_paths)
    
    # 有批次或队列非空 → 入队
    with self._watch_lock:
        self._watch_queue.extend(new_paths)
    return len(new_paths)
```

**验证**：
- 单测 `test_enqueue_from_watch_starts_when_idle`
- 单测 `test_enqueue_from_watch_queues_when_busy`
- 单测 `test_enqueue_from_watch_deduplicates_pending`

### 任务 3.3：_run 结尾续批逻辑

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py) 第 302 行附近

**改动**：在 `_finish(False)` 后插入检查
```python
self._finish(False)  # 现有代码

# 新增：检查监视队列
if not self._cancelled:
    with self._watch_lock:
        pending = list(self._watch_queue)
        self._watch_queue.clear()
        for p in pending:
            self._watch_pending.discard(str(p))
    if pending:
        self.start(pending)
```

**验证**：
- 单测 `test_run_continues_with_watch_queue_after_batch_finishes`
- 单测 `test_run_skips_continuation_when_cancelled`

### 任务 3.4：start 方法不变

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py) 第 113-128 行

**改动**：`start` 方法签名与行为完全不变，不接受空参数：
```python
def start(self, inputs: Sequence[Path]) -> bool:
    with self._condition:
        if self._busy:
            return False
        if not inputs:
            return False  # 不接受空参数（新增的显式检查）
        # ... 现有逻辑
```

> 注：现有代码实际行为已经是 `not inputs` 时返回（空列表进 `discover_images` 会被拒），这里只是把语义显式化。

**验证**：
- 现有 `test_batch_service_processes_all_images_and_persists_results` 通过
- 单测 `test_start_rejects_empty_inputs`

### 任务 3.5：pause/cancel 与队列交互

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py)

**改动**：修改 `cancel` 方法，清空监视队列：
```python
def cancel(self) -> bool:
    with self._condition:
        if not self._busy:
            return False
        self._cancelled = True
        self._paused = False
        self._condition.notify_all()
    # 新增：清空监视队列
    with self._watch_lock:
        self._watch_queue.clear()
        self._watch_pending.clear()
    return True
```

**验证**：
- 现有 `test_cancel_preserves_current_result_and_cancels_remaining` 通过
- 单测 `test_cancel_clears_watch_queue`（新行为）
- 单测 `test_pause_does_not_affect_watch_queue`

---

## 阶段 4：DesktopApi 桥接

### 任务 4.1：初始化 WatchFolderService

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py) 第 308-349 行

**改动**：`__init__` 末尾新增：
```python
self._watch_service = WatchFolderService(
    job_store=JobStore(self._job_database),
    event_sink=self._send_event,
)
self._watch_service.set_enqueue_callback(self._service.enqueue_from_watch)
```

**验证**：
- 现有 `test_desktop.py` 测试通过（需 mock WatchFolderService 或调整构造）
- 单测 `test_desktop_api_initializes_watch_service`

### 任务 4.2：桥接方法

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py)

**改动**：新增白名单方法：
```python
def list_watch_folders(self) -> list[dict]: ...
def add_watch_folder(self) -> dict | None: ...  # 弹文件夹选择对话框
def remove_watch_folder(self, path: str) -> None: ...
def set_watch_folder_enabled(self, path: str, enabled: bool) -> None: ...
```

每个方法都：
1. 调用 WatchFolderService 对应方法
2. 更新 UserSettings.watch_folders
3. 调用 SettingsStore.save 持久化

**验证**：
- 单测 `test_desktop_api_add_watch_folder_persists_to_settings`
- 单测 `test_desktop_api_remove_watch_folder_with_confirmation`

### 任务 4.3：启动序列集成（异步扫描）

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py) `bootstrap()` 方法附近

**改动**：
1. 在 `bootstrap()` 调用前启动监视服务与异步扫描：
   ```python
   self._watch_service.start()
   self._scan_cancel_event = threading.Event()
   self._scan_thread = threading.Thread(
       target=self._run_startup_scan,
       daemon=True,
       name="watch-folder-startup-scan",
   )
   self._scan_thread.start()
   ```
2. 新增 `_run_startup_scan` 方法：
   ```python
   def _run_startup_scan(self) -> None:
       self._send_event("watch_scan_started", {})
       try:
           pending = self._watch_service.rescan_existing(self._scan_cancel_event)
           if pending:
               self._service.enqueue_from_watch(pending)
       finally:
           self._send_event("watch_scan_complete", {
               "collected_count": len(pending) if 'pending' in locals() else 0,
               "cancelled": self._scan_cancel_event.is_set(),
           })
   ```
3. 新增 `cancel_watch_scan` 桥接方法（前端调用）：
   ```python
   def cancel_watch_scan(self) -> None:
       self._scan_cancel_event.set()
   ```
4. `bootstrap()` 返回字段新增：
   - `watch_folders: list[dict]`
   - `watch_scan_in_progress: bool`（`self._scan_thread.is_alive()`）

**验证**：
- 单测 `test_bootstrap_returns_watch_folders`
- 单测 `test_startup_scan_enqueues_unprocessed_files`
- 单测 `test_startup_scan_can_be_cancelled`
- 单测 `test_cancel_watch_scan_keeps_already_collected`

### 任务 4.4：退出钩子

**文件**：[app/desktop.py](file:///e:/消除车牌/app/desktop.py)

**改动**：
1. 新增 `shutdown(self) -> None` 方法：
   ```python
   def shutdown(self) -> None:
       self._watch_service.stop()
       self._service.wait(timeout=5.0)
   ```
2. 在 `launch()` 函数中注册 `window.events.closing += lambda: api.shutdown()`（或 pywebview 等效机制）

**验证**：
- 单测 `test_shutdown_stops_watch_service`
- smoke 测试：启动应用 → 关闭窗口 → 无残留进程

---

## 阶段 5：前端 UI

### 任务 5.1：设置页"监视文件夹"管理区块

**文件**：
- [app/web/index.html](file:///e:/消除车牌/app/web/index.html) 第 393 行附近（性能区块后）
- [app/web/styles/history-settings.css](file:///e:/消除车牌/app/web/styles/history-settings.css)
- [app/web/settings/settings.js](file:///e:/消除车牌/app/web/settings/settings.js)

**HTML 改动**：新增第 4 个区块
```html
<section class="settings-block">
  <h2>02 · 监视文件夹</h2>
  <div id="watch-folders-list"></div>
  <button id="add-watch-folder-button" class="secondary-button">+ 添加监视文件夹</button>
</section>
```

**CSS 改动**：
- `.watch-folder-row` 样式（路径 + 启停 + 移除按钮）
- 路径截断（`text-overflow: ellipsis`）+ hover 显示完整路径
- 沿用现有 token（`--surface`/`--border`/`--accent` 等）

**JS 改动**（settings.js）：
- 新增 `renderWatchFolders(folders)` 函数
- 新增 `addWatchFolder()` → `bridge.call("add_watch_folder")`
- 新增 `removeWatchFolder(path)` → 二次确认 → `bridge.call("remove_watch_folder", path)`
- 新增 `toggleWatchFolder(path, enabled)` → `bridge.call("set_watch_folder_enabled", path, enabled)`
- `hydrate()` 增加 `watch_folders` 字段处理

**验证**：
- 前端测试 `tests/frontend/settings-watch-folders.test.cjs`
- 手动验证：添加/启停/移除文件夹的完整流程

### 任务 5.2：空状态监视面板（方案 A）

**文件**：
- [app/web/index.html](file:///e:/消除车牌/app/web/index.html) 第 44-69 行（`#batch-empty`）
- [app/web/styles/batch.css](file:///e:/消除车牌/app/web/styles/batch.css)
- [app/web/batch/workspace.js](file:///e:/消除车牌/app/web/batch/workspace.js) `renderState()` 函数

**HTML 改动**：`#drop-zone` 内新增监视面板元素（默认隐藏）
```html
<div id="watch-panel" class="watch-panel" hidden>
  <div class="watch-radar"></div>
  <div class="watch-title">监视中</div>
  <div class="watch-sub" id="watch-sub-text">正在监视 0 个文件夹</div>
  <div class="watch-meta">
    <span>已捕获 <b id="watch-captured-count">0</b> 张</span>
    <span>已处理 <b id="watch-processed-count">0</b> 张</span>
  </div>
</div>
```

**CSS 改动**：
- `.watch-panel` 样式（虚线边框 + accent-soft 背景）
- `.watch-radar` 雷达图标（CSS 绘制）
- `prefers-reduced-motion` 时禁用脉冲动画

**JS 改动**（workspace.js `renderState()`）：
- 新增逻辑：当 `state.watchActive && !state.running` → 显示 `#watch-panel`，隐藏 `#drop-zone`
- 否则 → 显示 `#drop-zone`，隐藏 `#watch-panel`

**验证**：
- 前端测试 `tests/frontend/batch-watch-panel.test.cjs`
- 视觉证据：`docs/audits/v0.3.0/watch-folder-empty-panel.png`

### 任务 5.3：命令栏脉冲徽章（方案 B）

**文件**：
- [app/web/index.html](file:///e:/消除车牌/app/web/index.html) 第 72-102 行（命令栏）
- [app/web/styles/batch.css](file:///e:/消除车牌/app/web/styles/batch.css)
- [app/web/batch/workspace.js](file:///e:/消除车牌/app/web/batch/workspace.js)

**HTML 改动**：命令栏右侧新增徽章
```html
<span id="watch-indicator" class="watch-indicator" hidden>
  <span class="pulse-dot"></span>
  监视中 (<b id="watch-indicator-count">0</b>)
</span>
```

**CSS 改动**：
- `.watch-indicator` 徽章样式（accent-soft 背景 + accent 边框）
- `.pulse-dot` 脉冲动画（`@media (prefers-reduced-motion: no-preference)` 包裹）

**JS 改动**（workspace.js `renderState()`）：
- 新增逻辑：当 `state.watchActive` → 显示 `#watch-indicator`
- 点击徽章 → `PlateApp.navigate("settings")` + 滚动到监视文件夹区块

**验证**：
- 前端测试 `tests/frontend/batch-watch-indicator.test.cjs`
- 视觉证据：`docs/audits/v0.3.0/watch-folder-commandbar-badge.png`

### 任务 5.4：前端事件处理

**文件**：
- [app/web/core/state.js](file:///e:/消除车牌/app/web/core/state.js)
- [app/web/batch/workspace.js](file:///e:/消除车牌/app/web/batch/workspace.js) `receiveBackendEvent()`

**state.js 改动**：
- `initialState()` 新增字段：`watchActive: false`、`watchCaptured: 0`、`watchProcessed: 0`、`watchFolderCount: 0`
- `reduceBackendEvent` 新增事件分支：
  - `watch_status` → 更新 `watchActive`/`watchCaptured`/`watchProcessed`/`watchFolderCount`
  - `watch_folder_error` → 触发 toast + 标记文件夹 disabled

**workspace.js 改动**：
- `receiveBackendEvent` switch 新增 `watch_status` / `watch_folder_error` 分支
- 调用 `renderState()` 刷新 UI

**验证**：
- 前端测试 `tests/frontend/watch-events.test.cjs`

---

## 阶段 6：集成测试与视觉证据

### 任务 6.1：Python 单测完善

**文件**：[tests/unit/test_watch_folder_service.py](file:///e:/消除车牌/tests/unit/test_watch_folder_service.py)（新建）

**内容**：
- 阶段 2 所有单测集中到此文件
- Mock `ctypes` 调用，不依赖真实 win32 API
- 覆盖：watcher 检测、aggregator 稳定检测、去重各分支、错误恢复、rescan_existing

**文件**：[tests/unit/test_desktop.py](file:///e:/消除车牌/tests/unit/test_desktop.py)

**改动**：
- 阶段 3、4 所有单测追加到此文件
- 覆盖：enqueue_from_watch、_run 续批、start 微调、shutdown

### 任务 6.2：前端测试

**文件**：`tests/frontend/settings-watch-folders.test.cjs`、`tests/frontend/batch-watch-panel.test.cjs`、`tests/frontend/batch-watch-indicator.test.cjs`、`tests/frontend/watch-events.test.cjs`（新建）

**内容**：
- 使用 `node --test` 模式（延续现有惯例）
- Mock `PlateApp.bridge.call` 和 DOM

### 任务 6.3：集成测试 e2e

**文件**：[tests/integration/test_watch_folder_e2e.py](file:///e:/消除车牌/tests/integration/test_watch_folder_e2e.py)（新建）

**内容**（标记 `@pytest.mark.slow`）：
- `test_watch_folder_detects_new_file_and_processes`
- `test_watch_folder_redetects_modified_file`
- `test_watch_folder_disables_on_deletion`
- `test_startup_rescan_recovers_unprocessed_files`

**环境**：需要 Windows 真实文件系统，CI 跳过或标记 `@pytest.mark.skipif(not sys.platform.startswith("win"))`

### 任务 6.4：视觉证据收集

**目录**：`docs/audits/v0.3.0/`（新建）

**内容**：
- `watch-folder-settings.png`：设置页管理区块截图
- `watch-folder-empty-panel.png`：空状态监视面板截图
- `watch-folder-commandbar-badge.png`：命令栏脉冲徽章截图

**验证**：截图清晰展示 UI 状态，可用于 release checklist。

---

## 阶段 7：文档同步与回归

### 任务 7.1：用户指南更新

**文件**：[docs/user-guide.md](file:///e:/消除车牌/docs/user-guide.md)

**内容**：新增"监视文件夹"章节：
- 什么是监视文件夹
- 如何添加/移除/启停
- 适用场景（商拍现场持续倒入）
- 注意事项（本地磁盘、不监视 RAW）

### 任务 7.2：故障排除更新

**文件**：[docs/troubleshooting.md](file:///e:/消除车牌/docs/troubleshooting.md)

**内容**：新增故障场景：
- 监视文件夹不工作
- 文件夹被删除后如何恢复
- 启动扫描卡住

### 任务 7.3：隐私文档更新

**文件**：[docs/privacy.md](file:///e:/消除车牌/docs/privacy.md)

**内容**：
- 监视文件夹路径不写入诊断包
- 诊断包只统计数量，不导出路径

### 任务 7.4：发布检查清单更新

**文件**：[docs/release-checklist.md](file:///e:/消除车牌/docs/release-checklist.md)

**内容**：
- 累积 v0.3.0 监视文件夹的视觉证据
- 性能预算验证结果
- 测试覆盖率确认

### 任务 7.5：发布说明更新

**文件**：[RELEASE.md](file:///e:/消除车牌/RELEASE.md)

**内容**：v0.3.0 新增"监视文件夹"功能说明。

### 任务 7.6：全量回归

**命令**：
```bash
# Python 测试
python -m pytest tests/ -v

# 前端测试
node --test tests/frontend/

# Lint
ruff check app/ tests/
mypy app/

# Smoke 测试
python run.py --smoke
```

**退出条件**：
- 全量测试通过（141 → 更多，只增不减）
- Ruff + mypy 无错误
- Smoke 测试通过
- 至少一次真实样片处理验证
- 性能预算达标（入队延迟 ≤ 2s、启动扫描 ≤ 3s）

---

## 依赖关系图

```
0.1 Spec 修正
     │
     ▼
1.1 JobStore v5 ──┐
1.2 get_latest ───┤
1.3 UserSettings ─┤
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
2.1 骨架       3.1 字段       (1.x 测试)
     │             │
     ▼             ▼
2.2 Watcher    3.2 enqueue
     │             │
     ▼             ▼
2.3 Aggregator 3.3 续批
     │             │
     ▼             ▼
2.4 去重       3.4 start 微调
     │             │
     ▼             ▼
2.5 错误恢复   3.5 pause/cancel
     │             │
     ▼             │
2.6 rescan         │
     │             │
     ▼             │
2.7 事件推送       │
     │             │
     └──────┬──────┘
            ▼
     4.1 初始化 WatchFolderService
            │
            ▼
     4.2 桥接方法
            │
            ▼
     4.3 启动序列
            │
            ▼
     4.4 退出钩子
            │
     ┌──────┴──────┐
     ▼             ▼
5.1 设置页    5.2 空状态面板
     │             │
     ▼             ▼
5.3 命令栏徽章 5.4 事件处理
     │             │
     └──────┬──────┘
            ▼
     6.1 单测完善
            │
            ▼
     6.2 前端测试
            │
            ▼
     6.3 集成测试
            │
            ▼
     6.4 视觉证据
            │
            ▼
     7.1-7.5 文档同步
            │
            ▼
     7.6 全量回归
```

---

## 风险与决策点

### 决策点 1：win32 API 调用方式（阶段 2.2）

- **ctypes 直接调用**（推荐）：不增加依赖，但代码复杂
- **pywin32**：稳定但增加打包体积约 5MB
- **决策时机**：阶段 2.2 开始前

### 决策点 2：spec 第 13.2 节开放问题

1. cancel 后是否保留 `_watch_queue`（当前设计：保留）
2. `start` 传空参数消费队列（当前设计：接受）
3. 网络驱动器是否支持（当前设计：拒绝）
4. 启动扫描是否可取消（当前设计：不可取消）

**决策时机**：阶段 3.3、3.4 实现前确认

### 风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| ctypes 调用 ReadDirectoryChangesW 不稳定 | 中 | 高 | 阶段 6.3 集成测试充分覆盖；备选 pywin32 |
| schema v5 迁移破坏旧库 | 低 | 高 | 阶段 1.1 测试覆盖 v4→v5 迁移；备份机制 |
| 现有 141 测试回归 | 中 | 中 | 每阶段结束跑全量回归 |
| UI 改动影响现有布局 | 低 | 中 | 视觉证据 + 三档分辨率验证 |

---

## 估算

- 阶段 0：0.5 小时
- 阶段 1：3 小时
- 阶段 2：6 小时
- 阶段 3：3 小时
- 阶段 4：2 小时
- 阶段 5：4 小时
- 阶段 6：3 小时
- 阶段 7：2 小时

**总计**：约 23.5 小时（不含决策点讨论时间）

---

## 后续步骤

本计划经用户确认后：
1. 修正 spec 命名不一致（任务 0.1）
2. 从阶段 1.1 开始按依赖顺序实现
3. 每阶段结束跑全量回归
4. 阶段 6.3 集成测试通过后，可与用户确认是否进入下一子 spec（批量后处理）
