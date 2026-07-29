# 子 spec 4：历史搜索与前后对比

> 日期：2026-07-29
> 状态：待评审
> 版本：v0.3.0 子 spec 4
> 依赖：子 spec 3（项目/客户预设与归档）已设计，复用 `projects` 表与 `jobs.project_id` 外键；
> 替代当前历史页的 tab 切换式原图/结果查看

---

## 1. 目标

为历史页提供多维度搜索与筛选能力，并以前后并排对比视图替代当前的
"原图 / 结果" tab 切换。具体目标：

- 任务历史支持按状态、日期范围、文件名模糊、项目四维度组合查询
- 历史列表按项目分组展示（无项目的任务归入"未分组"）
- 选中任务后，原图与消除结果左右并排显示，支持滑块擦除对比与差分高亮
- 500 任务规模下查询响应 ≤ 200ms，列表滚动无明显卡顿

性能预算：500 任务组合查询 ≤ 200ms（含 SQLite 查询 + 序列化）。

---

## 2. 核心组件

```
HistorySearchService (后端查询服务)
   ├── QueryBuilder      组合 status / date / name / project 为 SQL
   └── ResultGrouper     按 project_id 分组，未分组归入"未分组"

前端 (app/web/components/)
   ├── FilterSidebar     筛选侧边栏，状态/日期/名称/项目四组控件
   ├── HistoryList       分组列表，虚拟滚动
   └── ComparisonView    左右并排 + 滑块对比 + 差分高亮
```

### 2.1 HistorySearchService

- 位于 `app/core/`，由 `app/desktop.py` 桥接暴露给前端
- 输入：`HistoryQuery` 对象（见 §4），全部字段可空，空字段不参与筛选
- 输出：分组后的任务列表，每项含 `job_id / name / status / created_at /
  project_id / project_name / original_path / result_path / post_processed_path`
- 查询构建：
  - 状态：`status IN (...)`（多选，空集合表示不过滤）
  - 日期：`created_at BETWEEN ? AND ?`（含端点，日期按本地时区起止）
  - 名称：`name LIKE ?`（前后加 `%`，大小写不敏感，使用 `COLLATE NOCASE`）
  - 项目：`project_id IN (...)`（多选，含 NULL 选项表示"未分组"）
- 排序：默认按 `created_at DESC`；用户可切换为 `name ASC`
- 分页：limit/offset，默认每页 50，前端滚动到底部加载下一页
- 分组：查询结果按 `project_id` 分组，`project_id IS NULL` 归入"未分组"，
  组内保持排序；分组顺序按组内最新任务时间倒序

### 2.2 ComparisonView

- 左右并排布局：左原图、右结果（后处理输出优先于原始消除输出，
  与子 spec 2 的 `post_processed_output` 优先级一致）
- 滑块对比模式：在并排视图之上叠加可拖拽竖直分割线，左半显示原图、
  右半显示结果，拖动分割线实时改变两侧可见区域
- 差分高亮：可切换的叠加层，基于像素差分（阈值可调，默认 30），
  将差异区域以半透明高亮框标注；差分在 Web Worker 中计算，不阻塞 UI
- 同步缩放：两侧图像共享缩放与平移状态，避免对比时错位
- 占位状态：结果未生成（处理中/失败）时，右侧显示对应状态占位图

### 2.3 FilterSidebar

- 位于历史页左侧，可折叠（折叠时仅显示筛选数量徽标）
- 四组控件自上而下：项目、状态、日期范围、文件名搜索
- 项目筛选：多选下拉，含"未分组"选项，按 `last_used_at` 倒序
- 状态筛选：多选 chip 组（排队中 / 处理中 / 已完成 / 失败 / 已取消）
- 日期范围：两个 date input（起 / 止），支持"今天 / 近 7 天 / 近 30 天"快捷预设
- 文件名搜索：单行输入框，输入后 300ms 防抖触发查询
- 筛选状态持久化：当前筛选条件存入 `localStorage`，重开历史页恢复

---

## 3. 数据模型影响

### 3.1 jobs.sqlite3

无新表。为支撑 500 任务规模下的组合查询性能，为 `projects` 关联与常用筛选列加索引：

```sql
CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
```

schema_version 不变（索引存在性以 `IF NOT EXISTS` 保证幂等，迁移脚本在
`app/core/job_store.py` 的 `_migrate` 中无条件执行）。

兼容性：旧库启动时自动补建索引，对已有数据无破坏。

### 3.2 settings.json

无新增字段。前端筛选状态仅存 `localStorage`，不进入 `settings.json`
（避免敏感的项目名出现在配置文件中，延续 §3.7 隐私约束）。

---

## 4. 后端桥接扩展

`app/desktop.py` 修改 `list_history` 方法签名，增加 `query` 参数：

```python
def list_history(
    self,
    query: dict | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "created_at_desc",
) -> dict:
    """
    query 字段（全部可空）:
      - statuses: list[str]       状态多选
      - date_from: str | None     ISO 日期，含端点
      - date_to: str | None       ISO 日期，含端点
      - name_contains: str | None 文件名模糊
      - project_ids: list[int | None]  项目多选，None 表示"未分组"
    返回:
      - groups: [{project_id, project_name, items: [...]}]
      - total: int                满足条件的任务总数（用于分页）
      - has_more: bool
    """
```

延续白名单 API 约束：方法只接收查询对象与分页参数，**不接收任意文件路径**；
返回的图片路径仍按现有脱敏策略，仅返回相对于工作区的相对路径。

新增辅助方法：

- `get_history_detail(job_id)` → 返回单个任务的对比视图所需完整信息
  （原图路径、原始输出、后处理输出、状态、尺寸、项目信息）

---

## 5. 前端架构

- 历史页重构为三栏布局：左侧 `FilterSidebar`、中间 `HistoryList`、
  右侧 `ComparisonView`（选中任务时展开，未选中时显示空态引导）
- 新组件放入 `app/web/components/`，遵循 `dialog.js` / `toast.js` 的模块模式
- 状态管理扩展 `app/web/core/state.js` 的 store 模式，新增 `historyFilter` slice
- `HistoryList` 采用虚拟滚动（仅渲染可视区 ± 缓冲行），500 任务列表首屏渲染 ≤ 100ms
- `ComparisonView` 的差分计算放入 Web Worker（`app/web/workers/diff.worker.js`），
  避免大图对比时阻塞主线程
- 图片加载采用 `loading="lazy"` + 占位骨架，避免一次性请求大量原图
- 延续无框架、无 CDN、CSP `connect-src 'none'` 约束，差分计算纯本地完成

---

## 6. 性能预算

| 指标 | 预算 | 说明 |
|---|---|---|
| 组合查询响应 | ≤ 200ms | 500 任务、含 4 维筛选，SQLite 查询 + 序列化 |
| 列表首屏渲染 | ≤ 100ms | 虚拟滚动，首屏 50 项 |
| 滚动帧率 | ≥ 55 fps | 虚拟滚动 + 图片懒加载 |
| 滑块拖动帧率 | ≥ 55 fps | transform 仅合成层，不触发布局 |
| 差分计算（1080p） | ≤ 300ms | Web Worker 内，不阻塞 UI |
| 分页加载下一页 | ≤ 150ms | 含网络往返（本地桥接） |

性能回归防护：`tests/performance/test_history_search.py` 内置 500 任务
fixture，CI 中断言查询响应 ≤ 200ms。

---

## 7. 测试边界

- `HistorySearchService` 查询单元测试：
  - 各筛选维度单独生效
  - 四维度组合（笛卡尔覆盖典型组合）
  - 空查询返回全量
  - "未分组"选项正确匹配 `project_id IS NULL`
  - 名称模糊的大小写不敏感、中文匹配
  - 日期端点含边界（当日 00:00:00 ~ 23:59:59）
- 分页与排序测试（limit/offset 边界、排序稳定性）
- 分组测试（任务跨多个项目的分组顺序）
- 索引幂等迁移测试（重复执行 `_migrate` 不报错）
- `ComparisonView` 前端组件测试：
  - 并排渲染正确性
  - 滑块拖动改变可见区域
  - 差分高亮开关切换
  - 结果未生成时的占位状态
- `FilterSidebar` 测试：
  - 300ms 防抖触发
  - 筛选状态 `localStorage` 持久化与恢复
  - 折叠/展开
- 性能测试：500 任务查询 ≤ 200ms（CI 强制）
- 集成测试：真实库筛选 → 前端列表 → 选中 → 对比视图端到端

---

## 8. 无障碍

- **键盘导航**：
  - `FilterSidebar` 内控件按 Tab 顺序可达，分组用 `fieldset` + `legend`
  - `HistoryList` 列表项支持上下方向键移动，Enter / Space 选中
  - `ComparisonView` 滑块支持左右方向键微调（步长 1%），Shift + 左右键步长 10%
  - 双击全屏退出键 Esc
- **ARIA 标签**：
  - 滑块容器 `role="slider"`，`aria-valuemin=0` `aria-valuemax=100` `aria-valuenow` 实时更新
  - 差分高亮开关 `role="switch"` `aria-checked`
  - 分组标题 `role="group"` + `aria-label`
  - 列表项 `role="listitem"`，含 `aria-label` 汇总任务名/状态/时间
  - 筛选数量徽标 `aria-live="polite"`，变更时朗读
- **屏幕阅读器友好**：
  - 对比视图为屏幕阅读器提供文本替代：朗读"原图与结果一致 / 差异区域 N 处"
  - 状态用图标 + 文本双表征，不依赖颜色单独传达状态
  - 日期输入提供 `aria-describedby` 格式提示
- **减少动效**：遵守 `prefers-reduced-motion`，滑块过渡与差分高亮淡入降级为瞬时切换
- **对比度**：筛选控件、滑块、徽标符合 WCAG AA（与子 spec 7 的可访问性收口衔接）

---

## 9. 隐私约束

- 筛选状态存 `localStorage`，**不**写入 `settings.json`，避免项目名出现在配置文件
- 诊断包不导出筛选历史、不导出项目名（延续总纲 §3.7）
- 差分计算的中间图像在 Web Worker 内处理完即释放，不写入磁盘
- 对比视图的图片加载沿用现有相对路径策略，不引入任何网络请求
- 项目名在历史列表中按用户可见性显示；导出诊断包时按子 spec 3 的脱敏规则处理
