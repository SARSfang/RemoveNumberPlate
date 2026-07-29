# 子 Spec 6：UI 升级 B — 信息架构与交互模式

> 日期：2026-07-29
> 状态：待评审
> 所属总纲：[2026-07-29-v0.3.0-master-design.md](./2026-07-29-v0.3.0-master-design.md)
> 推进顺序：第 6 项（共 7 项）
> 依赖：子 spec 5 的视觉规范与 token

---

## 1. 版本与范围

本子 spec 重构导航与新功能入口布局，定义动效系统与交互反馈模式，把四个 D 功能（监视文件夹、批量后处理、项目预设、历史搜索）的入口归位到信息架构的合适位置。

**在范围内**：

- 导航重构：四个 D 功能的入口归位
- 动效系统：150-220ms 过渡曲线、`prefers-reduced-motion` 支持
- 交互反馈：处理进度可视化、拖拽反馈、快捷键提示、错误状态
- 信息层级：主区域 / 侧边栏 / 命令栏 / 对话框的职责划分
- 快捷键体系扩展：`Ctrl+O` / `Ctrl+D` / `Ctrl+P` / `Esc` 等
- `app/web/core/shortcuts.js` 扩展
- `app/web/batch/workspace.js`、`app/web/history/history.js`、`app/web/settings/settings.js` 入口调整
- `app/web/components/` 新组件：进度可视化、拖拽 hint、快捷键提示

**不在范围内**：

- 视觉 token 与组件视觉规范（已在子 spec 5 定义）
- 响应式断点、高 DPI、ARIA 完整审查（留给子 spec 7）
- 任何后端 / 数据模型变更
- 任何新增网络请求

---

## 2. 已确认需求决策

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 导航范式 | 沿用顶部 topbar + 页面切换（不引入左侧主导航栏，避免大改） |
| 2 | 项目选择器位置 | 批处理页 topbar 右侧（与"开始批处理"按钮同行） |
| 3 | 监视文件夹入口 | 设置页第 4 区块 + 命令栏脉冲徽章（已在子 spec 1 定） |
| 4 | 批量后处理入口 | 批处理页命令栏"批处理完成"后的"后处理配置"按钮 + 向导弹出 |
| 5 | 历史搜索入口 | 历史页顶部筛选条 + 命令栏搜索图标 |
| 6 | 对比视图入口 | 历史页任务行的"对比"按钮 + 进入对比视图页 |
| 7 | 命令栏精简 | 保留主操作 + 状态指示；次要操作收到溢出菜单 |
| 8 | 动效曲线 | 主力 `--motion-ease-standard`；不使用 bounce / elastic |
| 9 | 快捷键提示 | 首次进入页面时浮层提示，可关闭；不再显示（写入 localStorage） |
| 10 | 错误状态呈现 | toast + 内联错误条双轨：瞬时错误走 toast，需用户决策的错误走对话框 |
| 11 | 拖拽反馈 | 拖入时 drop-zone 边框变 `--accent`、底色 `--accent-soft`、内部 hint 文字"松开入批" |
| 12 | 进度可视化 | 双层进度条：整体批次进度 + 当前照片处理阶段进度 |

---

## 3. 架构概览

### 3.1 实现方案

采用**方案 1：导航轻重构 + 交互模式规范化**。

```
┌─ app/web/ ──────────────────────────────────────────────────┐
│  app.js (扩展)                                              │
│    页面切换动效规范化                                        │
│  core/shortcuts.js (扩展)                                   │
│    新增：Ctrl+D / Ctrl+P / Esc 等全局快捷键                 │
│  core/state.js (扩展)                                       │
│    新增：command_bar / overflow_menu 状态切片                │
│  batch/workspace.js (扩展)                                  │
│    顶部增加项目选择器 + 后处理配置按钮                       │
│    进度条双层化 + 拖拽反馈                                   │
│  history/history.js (扩展)                                  │
│    顶部筛选条 + 对比视图入口                                 │
│  settings/settings.js (微调)                                │
│    监视文件夹区块（子 spec 1 已定位置）                      │
│  components/                                                │
│    progress.js (新)  双层进度可视化                          │
│    drop-hint.js (新) 拖拽反馈 hint                           │
│    shortcut-hint.js (新) 快捷键首次提示浮层                  │
│    overflow-menu.js (新) 命令栏溢出菜单                      │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 组件职责与依赖方向

- `shortcuts.js`：全局快捷键路由，按页面分派
- `state.js`：扩展 store，新增命令栏与溢出菜单状态
- `workspace.js` / `history.js` / `settings.js`：消费子 spec 5 的视觉规范，落实入口位置
- 新组件放入 `app/web/components/`，沿用 `dialog.js` / `toast.js` 的模块模式

**关键设计原则**：交互模式规范化——所有"按钮点击 → 反馈"路径走统一的状态机；不直接操作 DOM style，全部通过 class 切换。

### 3.3 方案对比（已评估）

| 方案 | 描述 | 评价 |
|---|---|---|
| **方案 1（采纳）** | 导航轻重构 + 交互模式规范化 | 沿用现有 topbar 架构；改动可控 |
| 方案 2 | 引入左侧主导航栏 + 面包屑 | 改动过大，与 v0.3.0 周期不符 |
| 方案 3 | 引入命令面板（Cmd+K） | YAGNI，工具型应用不强制命令面板 |

---

## 4. 导航重构

### 4.1 信息层级划分

```
┌──────────────────────────────────────────────────────────┐
│  Topbar (60px)                                           │
│  [Logo]  批处理  历史  设置            [项目: 客户A ▾]   │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  主区域 (页面内容)                                       │
│  ┌────────────────────────────────┐ ┌─────────────────┐ │
│  │  命令栏 (页面级操作)           │ │  侧边栏 (可选)  │ │
│  │  [开始] [暂停] [取消] [后处理] │ │  筛选 / 详情    │ │
│  └────────────────────────────────┘ │                 │ │
│  ┌────────────────────────────────┐ │                 │ │
│  │  内容区                        │ │                 │ │
│  │  - 批处理：预览 + filmstrip    │ │                 │ │
│  │  - 历史：列表 + 对比视图       │ │                 │ │
│  │  - 设置：分区块表单            │ │                 │ │
│  └────────────────────────────────┘ └─────────────────┘ │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  状态栏 (可选，批处理页显示进度)                         │
└──────────────────────────────────────────────────────────┘
```

**职责划分**：

| 区域 | 职责 | 不做 |
|---|---|---|
| Topbar | 全局导航 + 项目选择器 + 全局状态徽章 | 不放具体操作按钮 |
| 命令栏 | 当前页面的主操作（开始 / 暂停 / 取消 / 后处理配置 / 搜索） | 不放设置项 |
| 主区域 | 内容呈现（预览 / 列表 / 表单） | 不放主操作按钮 |
| 侧边栏 | 辅助信息（筛选 / 详情 / 历史搜索条件） | 不放主操作 |
| 对话框 | 一次性决策（确认 / 配置向导） | 不放常驻功能 |
| 状态栏 | 进度可视化 + 计数 | 不放操作按钮 |

### 4.2 四个 D 功能的入口归位

| 功能 | 入口位置 | 触发方式 |
|---|---|---|
| 监视文件夹 | 设置页第 4 区块 + topbar 脉冲徽章 | 设置页直接管理；徽章点击跳设置页 |
| 批量后处理 | 批处理页命令栏"后处理"按钮 | 批处理完成或暂停时出现；点击弹向导 |
| 项目预设 | topbar 右侧"项目"选择器 | 切换项目即套用预设；下拉底部"管理项目"跳设置页 |
| 历史搜索 | 历史页顶部筛选条 + topbar 搜索图标 | 直接输入；图标点击聚焦筛选条搜索框 |

### 4.3 topbar 重构细节

```
[Logo 消除车牌]  批处理  历史  设置              [●监视(2)] [项目:客户A ▾]
```

- 左侧：Logo + 三个页面 tab（批处理 / 历史 / 设置）
- 右侧：监视徽章（仅当有 enabled 监视时显示）+ 项目选择器
- tab 切换：当前页 `--accent` 底部 2px 指示条，过渡 200ms
- 项目选择器仅在批处理页和历史页显示（设置页隐藏）

### 4.4 命令栏精简策略

当前命令栏按钮过多时（≥5 个），将次要操作收到右侧"⋯"溢出菜单：

- 主操作（始终可见）：开始 / 暂停 / 取消
- 次要操作（收入溢出菜单）：后处理配置 / 重新处理 / 导出 / 全选 / 清除
- 溢出菜单触发：点击"⋯"按钮，弹出向下浮层
- 浮层动效：opacity + translateY(4px→0) 150ms `--motion-ease-decelerated`

### 4.5 页面切换动效

页面切换从当前的"瞬时显示"升级为淡入：

```css
.page {
  opacity: 0;
  transition: opacity var(--motion-base);
}
.page.is-active {
  opacity: 1;
}
```

- 不使用位移（避免布局抖动）
- `prefers-reduced-motion` 时降级为瞬时显示

---

## 5. 动效系统

### 5.1 时长与曲线规范

沿用子 spec 5 §6 定义：

| 场景 | 时长 | 曲线 |
|---|---|---|
| hover / focus 反馈 | 150ms | `--motion-ease-standard` |
| 面板展开 / 折叠 | 200ms | `--motion-ease-standard` |
| 对话框 / 抽屉 | 220ms | `--motion-ease-emphasized` |
| 命令栏按钮状态切换 | 150ms | `--motion-ease-standard` |
| 溢出菜单弹出 | 150ms | `--motion-ease-decelerated` |
| 拖拽 hint 出现 | 150ms | `--motion-ease-decelerated` |
| 进度条增长 | 200ms | `--motion-ease-standard` |
| 快捷键提示浮层 | 220ms | `--motion-ease-emphasized` |

### 5.2 prefers-reduced-motion 支持

```css
@media (prefers-reduced-motion: reduce) {
  /* 所有 transition 与 animation 降到 0.01ms */
  /* 仅保留颜色变化，禁用位移、缩放、脉冲 */
}
```

- 监视脉冲徽章降级为静态彩色点（沿用子 spec 1 §7.2 决策）
- 拖拽 hint 降级为瞬时颜色变化，无位移
- 进度条降级为离散更新（每 1% 跳一次）

### 5.3 动效使用边界

- **不使用动效掩盖性能问题**：处理延迟超过预算时优先优化代码，不用动画"安抚"
- **不使用循环动画**（除加载 spinner 和监视脉冲）
- **不使用视差动画**
- **所有动效必须可中断**：用户切换页面时立即停止当前动效

---

## 6. 交互反馈

### 6.1 处理进度可视化

`components/progress.js` 实现**双层进度条**：

```
┌─────────────────────────────────────────────┐
│  整体批次  ▓▓▓▓▓▓▓▓░░░░░░░░  43% (3/7)     │
│  当前照片  ▓▓▓▓▓▓▓▓▓▓▓▓░░░░  检测中        │
└─────────────────────────────────────────────┘
```

- 上层：整体批次进度（0-100%），数字格式 `43% (3/7)`
- 下层：当前照片处理阶段（检测 / 修复 / 写入），细条 + 阶段文字
- 颜色：0-99% `--accent`，100% `--success`
- 过渡：宽度 200ms `--motion-ease-standard`
- 阶段切换：颜色淡入 150ms
- 暂停态：进度条变为 `--warning` 条纹（`repeating-linear-gradient`）
- 取消态：进度条立即变 `--danger`，0.5 秒后隐藏

### 6.2 拖拽反馈

`components/drop-hint.js`：

- 用户拖文件进入窗口时：
  - `#drop-zone` 边框变为 2px `--accent`
  - 底色变为 `--accent-soft`
  - 中央 hint 文字变为"松开入批"（22px / 600）
  - hint 文字淡入 150ms
- 拖出窗口：
  - 状态恢复，hint 文字淡出 150ms
- 拖入非图片文件：
  - 边框变 `--warning`，hint 文字"仅支持 JPEG / PNG / TIFF"
- 拖入文件夹：
  - hint 文字"将递归扫描文件夹内图片"
  - 子 spec 1 监视功能已启用时，hint 增加"+ 按 Shift 添加为监视文件夹"

### 6.3 快捷键提示

`components/shortcut-hint.js`：

- 首次进入页面时，右下角浮层显示当前页主要快捷键
- 浮层动效：opacity + translateY(8px→0) 220ms `--motion-ease-emphasized`
- 浮层内容：快捷键 + 描述（如 `Ctrl+O  选择照片`）
- 关闭按钮："知道了"，点击后写入 `localStorage: shortcut_hint_dismissed_<page> = true`
- 用户再次访问同页面不再提示
- 设置页提供"重置快捷键提示"按钮（清除所有 `shortcut_hint_dismissed_*`）

### 6.4 错误状态

| 错误类型 | 呈现方式 | 持续 |
|---|---|---|
| 瞬时错误（如复制失败） | toast（沿用 `toast.js`） | 3 秒自动消失 |
| 输入校验错误 | 输入框下方红字 + 边框 `--danger-border` | 持续到修正 |
| 处理失败（单张） | filmstrip 该项 `--danger` 边框 + hover 显示错误信息 | 持续到重处理 |
| 处理失败（批次） | toast + 命令栏"重试"按钮 | 持续到用户操作 |
| 严重错误（如磁盘满） | 对话框（需用户决策） | 持续到用户确认 |
| 监视文件夹错误 | toast + 自动禁用对应文件夹 UI（子 spec 1 §7.5） | toast 3 秒；禁用持续 |

错误文案规范：
- 一句话说明"发生了什么"
- 一句话说明"用户能做什么"
- 不使用技术术语（如"OSError 28"），改为"磁盘空间不足，请清理后重试"

### 6.5 成功反馈

- 批处理完成：toast "批处理完成（N 张）" + 命令栏"打开输出目录"按钮
- 后处理完成：toast "已重命名 / 加水印 / 写入 EXIF（N 张）"
- 项目切换成功：项目选择器瞬时高亮 200ms
- 监视文件夹添加成功：toast + 列表新增项淡入 200ms

---

## 7. 快捷键体系

### 7.1 全局快捷键

| 快捷键 | 作用 | 备注 |
|---|---|---|
| `Ctrl+O` | 选择照片（打开文件选择对话框） | 沿用现有 |
| `Ctrl+D` | 选择文件夹（打开文件夹选择对话框） | 新增 |
| `Ctrl+P` | 暂停 / 继续当前批次 | 新增；批处理页激活 |
| `Esc` | 取消当前操作 / 关闭对话框 / 退出对比视图 | 新增 |
| `Ctrl+,` | 跳转设置页 | 新增 |
| `Ctrl+1` | 跳转批处理页 | 新增 |
| `Ctrl+2` | 跳转历史页 | 新增 |
| `Ctrl+3` | 跳转设置页 | 新增（与 `Ctrl+,` 等效） |

### 7.2 批处理页快捷键

| 快捷键 | 作用 | 备注 |
|---|---|---|
| `←` / `→` | 上一张 / 下一张 | 沿用现有 |
| `Home` / `End` | 跳到首张 / 末张 | 沿用现有 |
| `1` | 切到"原图"标签 | 沿用现有 |
| `2` | 切到"结果"标签 | 沿用现有 |
| `F` | 跟随最新 | 沿用现有 |
| `Ctrl+Enter` | 开始批处理 | 新增 |
| `Ctrl+Shift+P` | 后处理配置 | 新增 |

### 7.3 历史页快捷键

| 快捷键 | 作用 | 备注 |
|---|---|---|
| `Ctrl+F` | 聚焦筛选条搜索框 | 新增 |
| `Enter` | 打开选中任务的对比视图 | 新增 |
| `←` / `→` | 上一条 / 下一条任务 | 新增 |
| `Esc` | 退出对比视图 / 清空筛选 | 新增 |

### 7.4 对比视图快捷键

| 快捷键 | 作用 | 备注 |
|---|---|---|
| `←` / `→` | 移动滑块 | 新增；步长 5% |
| `Shift+←` / `Shift+→` | 移动滑块（大步） | 新增；步长 20% |
| `D` | 切换差分高亮 | 新增 |
| `Esc` | 退出对比视图 | 新增 |

### 7.5 设置页快捷键

| 快捷键 | 作用 | 备注 |
|---|---|---|
| `Ctrl+S` | 保存设置 | 新增 |
| `Esc` | 取消未保存修改 | 新增 |

### 7.6 快捷键冲突规则

- 全局快捷键优先级 > 页面快捷键
- 对话框打开时，仅 `Esc` 和对话框内快捷键生效
- 输入框聚焦时，所有快捷键失效（除 `Esc`）
- 沿用 `shortcuts.js` 的 `isTypingTarget` / `dialogOpen` 判断

### 7.7 shortcuts.js 扩展

```javascript
function handleGlobal(event) {
  // Ctrl+O 选择照片
  if (event.ctrlKey && event.key.toLowerCase() === "o") {
    event.preventDefault();
    PlateApp.batch.chooseFiles();
    return;
  }
  // Ctrl+D 选择文件夹（新增）
  if (event.ctrlKey && event.key.toLowerCase() === "d") {
    event.preventDefault();
    PlateApp.batch.chooseFolder();
    return;
  }
  // Ctrl+P 暂停/继续（新增）
  if (event.ctrlKey && event.key.toLowerCase() === "p") {
    if (activePage() === "batch") {
      event.preventDefault();
      PlateApp.batch.togglePause();
    }
    return;
  }
  // Ctrl+, 跳转设置页（新增）
  if (event.ctrlKey && event.key === ",") {
    event.preventDefault();
    PlateApp.app.switchPage("settings");
    return;
  }
  // Ctrl+1/2/3 页面切换（新增）
  if (event.ctrlKey && ["1", "2", "3"].includes(event.key)) {
    event.preventDefault();
    const pages = ["batch", "history", "settings"];
    PlateApp.app.switchPage(pages[Number(event.key) - 1]);
    return;
  }
  // Esc 取消/关闭（新增）
  if (event.key === "Escape") {
    if (dialogOpen()) {
      PlateApp.dialog.close();
    } else if (PlateApp.comparison && PlateApp.comparison.isActive()) {
      PlateApp.comparison.close();
    } else if (activePage() === "history") {
      PlateApp.history.clearFilters();
    }
    return;
  }
}
```

---

## 8. 信息层级细化

### 8.1 命令栏状态机

```
[空状态] ──拖入/选择──> [待处理] ──开始──> [运行中] ──完成──> [完成]
                              ↑                  │
                              ├──暂停──> [暂停] ─┘
                              │                  │
                              └──取消──> [空状态或待处理]
                                                 │
                                          [后处理配置按钮出现]
```

每个状态对应命令栏按钮的可见性与启用性：

| 状态 | 开始 | 暂停 | 取消 | 后处理 |
|---|---|---|---|---|
| 空状态 | 禁用 | 隐藏 | 隐藏 | 隐藏 |
| 待处理 | 启用 | 隐藏 | 隐藏 | 隐藏 |
| 运行中 | 隐藏 | 启用 | 启用 | 隐藏 |
| 暂停 | 隐藏 | 启用（继续） | 启用 | 隐藏 |
| 完成 | 重置为空状态 | 隐藏 | 隐藏 | 启用 |

### 8.2 侧边栏策略

- 批处理页：无侧边栏（filmstrip 在底部）
- 历史页：右侧边栏（详情 / 对比视图触发时滑入），宽度 360px
- 设置页：无侧边栏（垂直分区块）

侧边栏滑入：

```css
.sidebar {
  transform: translateX(100%);
  transition: transform var(--motion-slow);
}
.sidebar.is-open {
  transform: translateX(0);
}
```

### 8.3 对话框层级

- z-index 规范：
  - 0：页面内容
  - 10：命令栏、topbar
  - 20：侧边栏
  - 30：toast
  - 40：对话框遮罩
  - 50：对话框内容
  - 60：快捷键提示浮层

---

## 9. 数据模型影响

**无**（纯前端）。

- 不修改 `app/core/job_store.py`
- 不修改 `settings.json` schema
- 不修改 `app/desktop.py` 白名单 API
- `localStorage` 仅用于快捷键提示 dismissed 状态（用户偏好，不进入 settings.json）

---

## 10. 测试边界

### 10.1 前端组件单元测试

`tests/frontend/*.test.cjs`（`node --test` 模式）：

- `progress.test.cjs`：双层进度条状态切换（运行中 / 暂停 / 完成 / 取消）
- `drop-hint.test.cjs`：拖入文件 / 文件夹 / 非图片的反馈切换
- `shortcut-hint.test.cjs`：首次显示 / dismissed 后不显示 / 重置
- `overflow-menu.test.cjs`：溢出菜单展开 / 关闭 / 选项点击
- `command-bar-state.test.cjs`：命令栏状态机各状态按钮可见性
- `shortcuts.test.cjs`：全局 / 批处理 / 历史 / 对比视图快捷键分派

### 10.2 交互流程验证

`tests/frontend/*.test.cjs`：

- `flow-batch-keyboard.test.cjs`：键盘走完整批处理流程（Ctrl+O → Enter → Ctrl+P → Esc）
- `flow-history-search.test.cjs`：键盘走历史搜索流程（Ctrl+2 → Ctrl+F → 输入 → Enter → Esc）
- `flow-comparison.test.cjs`：键盘走对比视图流程（Enter → ←/→ → D → Esc）
- `flow-mouse-drop.test.cjs`：鼠标拖拽反馈（dragenter / dragover / dragleave / drop）
- `flow-touchpad.test.cjs`：触摸板模拟（pointerdown / pointermove / pointerup）

### 10.3 集成测试

`tests/integration/`：

- `test_ui_navigation_e2e.py`（`@pytest.mark.slow`）：
  - 启动桌面端，通过模拟点击验证页面切换动效不阻塞
  - 验证 topbar 项目选择器在批处理 / 历史页可见、设置页隐藏

### 10.4 视觉证据

`docs/audits/v0.3.0/`：

- `ui-b-topbar-project-selector.png`：topbar 项目选择器展开
- `ui-b-command-bar-overflow.png`：命令栏溢出菜单展开
- `ui-b-progress-double-layer.png`：双层进度条稳态
- `ui-b-drop-hint.png`：拖拽 hint 激活态
- `ui-b-shortcut-hint.png`：快捷键提示浮层
- `ui-b-error-toast.png`：错误 toast
- `ui-b-error-dialog.png`：严重错误对话框
- `ui-b-sidebar-history.png`：历史页侧边栏滑入

### 10.5 不在测试范围内

- 视觉 token 一致性（已在子 spec 5 §11.2 覆盖）
- 像素级视觉回归（留给子 spec 7）
- ARIA 完整审查（留给子 spec 7）

---

## 11. 性能预算

| 指标 | 预算 | 测量方式 |
|---|---|---|
| 页面切换动效延迟 | ≤ 50ms（不含 200ms 过渡本身） | DevTools Performance |
| 拖拽反馈响应延迟 | ≤ 16ms（一帧内） | dragenter 到 hint 出现 |
| 快捷键响应延迟 | ≤ 50ms | keydown 到动作执行 |
| 进度条更新频率 | ≤ 60fps（每帧最多一次） | requestAnimationFrame 节流 |
| 新增 JS 体积 | ≤ 12 KB（gzip 前，全部新组件） | 文件大小 |
| 现有 P50 2.38s 推理基线 | 不变 | 不修改处理路径 |

---

## 12. 隐私与离线约束

- 不引入任何网络请求（CSP `connect-src 'none'` 不变）
- `localStorage` 仅存快捷键提示 dismissed 标志，不含用户数据
- 不引入任何外网资源
- 拖拽 hint 与快捷键提示文案不包含用户文件路径

---

## 13. 风险与未决项

### 13.1 风险

| 风险 | 缓解措施 |
|---|---|
| 快捷键与浏览器 / 系统冲突 | `Ctrl+D`（浏览器书签）在桌面 webview 中不冲突；`Ctrl+P`（打印）在桌面 webview 中拦截 |
| 命令栏状态机复杂导致 bug | 用显式状态枚举，禁止隐式状态转换；单元测试覆盖所有转换 |
| 拖拽反馈在触摸板上的差异 | pointer events 统一处理鼠标 / 触摸板 / 触摸 |
| 进度条频繁更新引起重绘 | requestAnimationFrame 节流；仅 transform / opacity |
| 监视脉冲徽章在 reduced-motion 下未降级 | 沿用子 spec 1 §7.2 决策；测试覆盖 |

### 13.2 已决策的开放问题

1. **是否引入命令面板（Cmd+K）？**
   - 决策：**不引入**。工具型应用，YAGNI。
   - 依据：用户决策（2026-07-29）

2. **项目选择器是否在设置页也显示？**
   - 决策：**不显示**。设置页无项目上下文需求。
   - 依据：用户决策（2026-07-29）

3. **快捷键提示是否每次启动都显示？**
   - 决策：**不每次**。首次访问每个页面时显示一次，dismissed 后不再显示；设置页提供重置。
   - 依据：用户决策（2026-07-29）

4. **拖拽 hint 是否提示"添加为监视文件夹"（Shift 修饰）？**
   - 决策：**提示**。仅在监视功能已启用至少一个文件夹时显示该提示。
   - 依据：用户决策（2026-07-29）

5. **历史页侧边栏是常驻还是按需？**
   - 决策：**按需**。点击任务行的"详情"或"对比"时滑入。
   - 依据：用户决策（2026-07-29）

---

## 14. 后续步骤

本子 spec 经用户 review 通过后：

1. 修正/确认第 13.2 节的开放问题
2. 交接到 writing-plans 制定实现计划
3. 按计划：先扩展 `shortcuts.js` → 实现新组件 → 调整入口位置 → 交互流程测试 → 视觉证据
4. 完成后进入子 spec 7（UI 升级 C：响应性与可访问性收口）
