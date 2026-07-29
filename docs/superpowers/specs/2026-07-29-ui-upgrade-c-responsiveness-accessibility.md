# 子 Spec 7：UI 升级 C — 响应性与可访问性收口

> 日期：2026-07-29
> 状态：待评审
> 所属总纲：[2026-07-29-v0.3.0-master-design.md](./2026-07-29-v0.3.0-master-design.md)
> 推进顺序：第 7 项（共 7 项）
> 依赖：子 spec 5 的视觉规范、子 spec 6 的信息架构与交互模式

---

## 1. 版本与范围

本子 spec 完成 v0.3.0 UI 升级的最后一公里：多分辨率适配、高 DPI 资源、窄窗口策略、键盘导航完整性、ARIA 全面审查与修复，确保工具在不同硬件与使用场景下的可用性。

**在范围内**：

- 响应式断点规范：1040×680 / 1280×820 / 1920×1080 三档
- 高 DPI 资源：图标 SVG、字体渲染
- 窄窗口策略：侧边栏折叠、面板堆叠、命令栏精简
- 键盘导航完整性：Tab 顺序、焦点可见性、快捷键
- ARIA 角色与标签审查：每个交互元素都有正确的 role 和 aria-label
- `prefers-reduced-motion`：动效降级或禁用
- `prefers-contrast`：高对比度模式支持
- 颜色对比度：WCAG AA 标准（4.5:1 文字、3:1 大文字）
- 三档分辨率视觉回归

**不在范围内**：

- 视觉 token 与组件视觉规范（已在子 spec 5 定义）
- 信息架构与交互模式（已在子 spec 6 定义）
- 触摸屏手势（产品定位为桌面端，不做触摸优化）
- 国际化（i18n）布局镜像（留给后续版本）
- 任何后端 / 数据模型变更
- 任何新增网络请求

---

## 2. 已确认需求决策

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 最小分辨率 | 1040×680（保证功能可用，不保证最优体验） |
| 2 | 标准分辨率 | 1280×820（设计基准） |
| 3 | 宽屏分辨率 | 1920×1080（充分利用空间，不刻意扩展功能） |
| 4 | 低于最小分辨率 | 允许运行但显示"建议分辨率"提示，不阻塞 |
| 5 | 高 DPI 策略 | 全部图标走 SVG（自动缩放）；字体走系统渲染，不内置位图字体 |
| 6 | 窄窗口侧边栏 | < 1280px 自动折叠为图标栏，点击展开为浮层 |
| 7 | 窄窗口命令栏 | < 1280px 次要操作进溢出菜单（沿用子 spec 6 §4.4） |
| 8 | ARIA 范围 | 全量审查所有交互元素，符合 WAI-ARIA 1.1 |
| 9 | 对比度标准 | WCAG AA（4.5:1 正文、3:1 大文字与图形元素） |
| 10 | prefers-contrast | 支持 `more` / `high` 值，提供高对比度样式覆盖 |
| 11 | 焦点可见性 | 所有交互元素 focus 时必须有可见焦点环（`--shadow-focus`） |
| 12 | 屏幕阅读器测试范围 | NVDA（Windows，主目标）；不强制测试 JAWS / VoiceOver |
| 13 | 颜色不作为唯一信息载体 | 状态色搭配图标 / 文字（如"成功 ✓"、"失败 ✗"） |

---

## 3. 架构概览

### 3.1 实现方案

采用**方案 1：断点驱动 + 媒体查询 + ARIA 全量补齐**。

```
┌─ app/web/styles/ ───────────────────────────────────────────┐
│  tokens.css (扩展)                                          │
│    新增：断点 token (--bp-min / --bp-std / --bp-wide)        │
│    新增：高对比度色板 (--hc-*)                               │
│  base.css (扩展)                                            │
│    高 DPI 字体渲染优化                                       │
│    prefers-contrast 覆盖                                    │
│  components.css (扩展)                                      │
│    断点响应式覆盖                                            │
│    焦点环统一                                                │
│  responsive.css (新建)                                      │
│    断点策略（窄窗口折叠 / 堆叠 / 精简）                       │
│  high-contrast.css (新建)                                   │
│    prefers-contrast 覆盖样式                                 │
└─────────────────────────────────────────────────────────────┘

┌─ app/web/ ──────────────────────────────────────────────────┐
│  app.js (扩展)                                              │
│    断点检测 + 窗口 resize 监听                               │
│  core/state.js (扩展)                                       │
│    新增：viewport 状态切片 ({width, height, breakpoint})    │
│  components/                                                │
│    a11y-audit.js (新)  ARIA 自检工具（开发期）              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 组件职责与依赖方向

- `responsive.css`：消费子 spec 5 token，定义断点行为
- `high-contrast.css`：覆盖颜色 token，不重写布局
- `app.js`：监听 resize，更新 state.viewport，触发 UI 适配
- 子 spec 7 不引入新组件，只对已有组件做响应式与可访问性增强

**关键设计原则**：移动优先的反向——桌面优先，向下兼容到 1040×680；可访问性是默认属性，不是可选附加。

### 3.3 方案对比（已评估）

| 方案 | 描述 | 评价 |
|---|---|---|
| **方案 1（采纳）** | 断点驱动 + 媒体查询 + ARIA 全量补齐 | 沿用现有 CSS 架构；改动可控 |
| 方案 2 | 引入 CSS Container Queries | 浏览器支持参差；现有 webview 不保证 |
| 方案 3 | JS 驱动响应式（resize 时重渲染） | 性能差；与现有无框架架构不匹配 |

---

## 4. 响应式断点规范

### 4.1 断点定义

```css
/* tokens.css 新增 */
--bp-min-width: 1040px;
--bp-min-height: 680px;
--bp-std-width: 1280px;
--bp-std-height: 820px;
--bp-wide-width: 1920px;
--bp-wide-height: 1080px;
```

媒体查询：

```css
/* 窄窗口（< 1280px） */
@media (max-width: 1279px) { ... }

/* 标准窗口（1280px - 1919px） */
@media (min-width: 1280px) and (max-width: 1919px) { ... }

/* 宽屏（≥ 1920px） */
@media (min-width: 1920px) { ... }

/* 低于最小（< 1040px） */
@media (max-width: 1039px) { ... }
```

### 4.2 三档分辨率行为差异

| 元素 | 窄窗口（1040-1279） | 标准窗口（1280-1919） | 宽屏（1920+） |
|---|---|---|---|
| Topbar | 全部显示 | 全部显示 | 全部显示 |
| 项目选择器 | 显示（缩略：仅项目名） | 显示（项目名 + 客户名） | 显示（项目名 + 客户名 + 时间） |
| 命令栏 | 主操作 + 溢出菜单 | 主操作 + 次要操作 | 主操作 + 次要操作 + 快捷键提示 |
| 历史页侧边栏 | 折叠为图标栏 | 默认隐藏，按需滑入 | 默认展开 |
| 批处理预览 | 自适应缩放 | 自适应缩放 | 居中最大 1600px |
| Filmstrip | 高度 120px | 高度 156px | 高度 156px + 双行 |
| 设置页 | 单列 | 单列 | 双列（左导航 + 右内容） |
| 对比视图 | 上下堆叠 | 左右并排 | 左右并排 + 差分面板 |

### 4.3 低于最小分辨率

- 应用允许启动，不阻塞
- 启动时检测 `window.innerWidth < 1040 || window.innerHeight < 680`
- 显示一次性 toast："建议分辨率 1280×820 以上，当前窗口可能影响体验"
- 用户调整窗口大小达到最小后，toast 不再出现（session 内）

### 4.4 窗口状态记忆

- 用户调整窗口大小后，state.viewport 实时更新
- 关闭应用时不持久化窗口尺寸（沿用现有行为，不新增 settings 字段）
- 重新启动时使用系统默认窗口尺寸

---

## 5. 高 DPI 资源

### 5.1 图标策略

- 所有图标走 SVG（沿用现有 `app/web/assets/*.svg` 模式）
- SVG 使用 `currentColor`，自动跟随文字颜色
- SVG `width` / `height` 不写死，由 CSS `font-size` 或显式尺寸控制
- 不内置 @1x / @2x / @3x 位图（YAGNI）

### 5.2 字体渲染优化

`base.css` 新增：

```css
html {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
  font-feature-settings: "tnum" 1, "kern" 1;
}
```

- `tnum`：等宽数字（计数 / 进度数字对齐）
- `kern`：字距优化
- 高 DPI 屏幕下字体渲染更清晰
- 不影响低 DPI 屏幕（系统自然渲染）

### 5.3 图片资源

- 用户照片：原始分辨率，由 `img` 标签自适应
- 占位图 / 空状态图：SVG（自动缩放）
- Logo：SVG
- 不内置任何位图资源（除用户照片）

### 5.4 devicePixelRatio 处理

- 不主动检测 `devicePixelRatio`
- 所有布局基于 CSS 像素，浏览器自动处理物理像素映射
- 拖拽坐标转换：`event.clientX` 已是 CSS 像素，无需手动换算

---

## 6. 窄窗口策略

### 6.1 侧边栏折叠

历史页侧边栏在窄窗口下：

```
[宽窗口]                    [窄窗口]
┌────────┬──────────┐       ┌────────────────┐
│        │          │       │                │
│ 主内容 │ 侧边栏   │       │  主内容        │ [☰]
│        │          │       │                │
└────────┴──────────┘       └────────────────┘
                                  ↓ 点击 [☰]
                            ┌────────────────┐
                            │  主内容（遮罩）│
                            │  ┌──────────┐  │
                            │  │ 侧边栏   │  │
                            │  │ (浮层)   │  │
                            │  └──────────┘  │
                            └────────────────┘
```

- < 1280px：侧边栏默认隐藏，topbar 显示"☰"按钮
- 点击"☰"：侧边栏以浮层形式从右侧滑入，遮罩 `--scrim`
- 点击遮罩或按 Esc：侧边栏滑出
- 滑入动效：transform translateX(100%→0) 220ms `--motion-ease-emphasized`

### 6.2 面板堆叠

批处理页在窄窗口下：

- 预览区与 filmstrip 上下堆叠（沿用现有垂直布局）
- 预览区最小高度 320px
- filmstrip 高度从 156px 降至 120px
- 命令栏按钮溢出到"⋯"菜单（子 spec 6 §4.4）

### 6.3 命令栏精简

```css
@media (max-width: 1279px) {
  .command-bar .secondary-action {
    display: none;  /* 隐藏次要操作 */
  }
  .command-bar .overflow-menu-trigger {
    display: inline-flex;  /* 显示溢出菜单触发 */
  }
}

@media (min-width: 1280px) {
  .command-bar .secondary-action {
    display: inline-flex;
  }
  .command-bar .overflow-menu-trigger {
    display: none;
  }
}
```

### 6.4 设置页堆叠

宽屏设置页（≥ 1920px）支持双列：

```
[宽屏]
┌────────────┬─────────────────────┐
│ 01 · 处理  │ 处理参数表单        │
│ 02 · 性能  │                     │
│ 03 · 监视  │                     │
│ 04 · 数据  │                     │
└────────────┴─────────────────────┘
```

- 左侧导航固定 240px
- 右侧内容自适应
- < 1920px：单列垂直布局（沿用现有）

---

## 7. 键盘导航完整性

### 7.1 Tab 顺序

每个页面遵循"从上到下、从左到右"的自然 Tab 顺序：

| 页面 | Tab 顺序 |
|---|---|
| 批处理 | topbar 页面 tab → 项目选择器 → 命令栏按钮（主→次）→ 预览区 → filmstrip → 溢出菜单 |
| 历史 | topbar 页面 tab → 项目选择器 → 筛选条（状态→日期→项目→搜索→清除）→ 任务列表 → 侧边栏触发 |
| 设置 | topbar 页面 tab → 设置区块 1→2→3→4 → 各区块内表单字段 |
| 对比视图 | 关闭按钮 → 滑块 → 差分切换 → 上一张/下一张 |

### 7.2 焦点可见性

```css
/* 所有交互元素 */
:focus-visible {
  outline: none;
  box-shadow: var(--shadow-focus);
}

/* 非交互元素不显示焦点 */
*:focus:not(:focus-visible) {
  outline: none;
  box-shadow: none;
}
```

- 使用 `:focus-visible` 而非 `:focus`，避免鼠标点击时残留焦点环
- 焦点环使用 `--shadow-focus`（沿用子 spec 5 §4.4）
- 焦点环颜色 `--focus`（`--blue-300`），在深色背景上对比度 ≥ 4.5:1
- 禁用 `outline: none` 全局重置；仅 `:focus-visible` 时移除原生 outline 改用 box-shadow

### 7.3 焦点陷阱

对话框打开时：

- 焦点自动移到对话框主操作按钮
- Tab 循环限于对话框内（focus trap）
- Shift+Tab 反向循环
- Esc 关闭对话框，焦点返回触发元素

### 7.4 跳过链接（Skip Link）

每个页面顶部添加"跳到主内容"链接：

```html
<a href="#main-content" class="skip-link">跳到主内容</a>
```

- 默认 `sr-only`，Tab 聚焦时变为可见
- 点击后焦点移到 `#main-content`，再次 Tab 从主内容开始

### 7.5 快捷键完整性

子 spec 6 §7 定义的所有快捷键必须可在无鼠标情况下完成全部操作：
- 选择照片 / 文件夹
- 开始 / 暂停 / 取消批处理
- 切换页面
- 历史搜索
- 进入 / 退出对比视图
- 后处理配置向导

---

## 8. ARIA 角色与标签审查

### 8.1 审查范围

全量审查 `app/web/**/*.js` 渲染的 DOM，每个交互元素必须有：
- 正确的 `role`（如 `button` / `tab` / `dialog` / `progressbar`）
- 描述性的 `aria-label`（图标按钮必须）
- 必要时的 `aria-describedby`（指向说明文字）
- 状态变化时的 `aria-expanded` / `aria-selected` / `aria-pressed`

### 8.2 关键组件 ARIA 规范

| 组件 | role | 必需 ARIA |
|---|---|---|
| 顶部 tab 导航 | `tablist` + `tab` | `aria-selected` |
| 项目选择器 | `combobox` + `listbox` + `option` | `aria-expanded`、`aria-selected` |
| 命令栏按钮 | `button` | `aria-label`（图标按钮）、`aria-pressed`（切换按钮） |
| 溢出菜单 | `menu` + `menuitem` | `aria-haspopup`、`aria-expanded` |
| 双层进度条 | `progressbar` | `aria-valuenow`、`aria-valuemin`、`aria-valuemax`、`aria-label` |
| Filmstrip | `listbox` + `option` | `aria-selected`、`aria-label`（每项"第 N 张，状态 X"） |
| 对比视图滑块 | `slider` | `aria-valuenow`、`aria-valuemin`、`aria-valuemax`、`aria-label` |
| 对话框 | `dialog` | `aria-modal="true"`、`aria-labelledby`（指向标题） |
| Toast | `status` 或 `alert` | `aria-live="polite"`（status）/ `aria-live="assertive"`（alert） |
| 监视脉冲徽章 | `status` | `aria-live="polite"`、`aria-label="监视 N 个文件夹"` |
| 侧边栏 | `complementary` | `aria-label="任务详情"` |
| 拖拽区域 | `application` | `aria-label="拖入照片或文件夹"` |
| 快捷键提示浮层 | `dialog` | `aria-labelledby` |

### 8.3 图标按钮 aria-label 示例

```html
<!-- 错误：屏幕阅读器读"按钮" -->
<button class="icon-button"><svg>...</svg></button>

<!-- 正确：屏幕阅读器读"暂停按钮" -->
<button class="icon-button" aria-label="暂停">
  <svg aria-hidden="true">...</svg>
</button>
```

### 8.4 装饰性元素

- 纯装饰 SVG：`aria-hidden="true"`
- 重复信息：用 `aria-hidden` 隐藏重复文字（如已有 aria-label 的按钮内文字）
- 状态指示点：用 `aria-label` 替代颜色，如 `<span class="dot" aria-label="启用"></span>`

### 8.5 动态内容公告

- toast 出现：`aria-live="polite"` 区域自动公告
- 错误对话框：`aria-live="assertive"`（焦点自动移到对话框）
- 进度条更新：不公告每次变化；仅在完成时公告"批处理完成"
- 监视文件夹检测到新文件：不公告（避免骚扰）；仅状态徽章计数更新

### 8.6 屏幕阅读器测试

主目标：NVDA（Windows，免费）

测试场景：
1. 启动应用 → 听到"消除车牌，批处理页"
2. Tab 导航 → 听到每个按钮的 label
3. 开始批处理 → 听到"批处理开始，进度 0%"
4. 完成批处理 → 听到"批处理完成，7 张"
5. 切换历史页 → 听到"历史页，N 条任务"
6. 打开对比视图 → 听到"对比视图，原图与结果并排"
7. 错误发生 → 听到"错误：磁盘空间不足"
8. 对话框 → 听到对话框标题，焦点自动落在主操作

---

## 9. prefers-reduced-motion

### 9.1 沿用子 spec 5 §6.2

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

### 9.2 额外降级

- 子 spec 6 §5.2 定义的动效降级全部生效
- 拖拽 hint 降级为瞬时颜色变化
- 进度条降级为离散更新
- 监视脉冲徽章降级为静态彩色点
- 页面切换降级为瞬时显示
- 侧边栏滑入降级为瞬时显示

### 9.3 检测方式

- CSS 媒体查询自动生效
- JS 检测：`window.matchMedia('(prefers-reduced-motion: reduce)').matches`
- 用户可在系统设置中开启（Windows: 设置 → 辅助功能 → 视觉效果 → 动画效果）

---

## 10. prefers-contrast

### 10.1 支持的值

- `no-preference`（默认）
- `more`：增强对比度
- `high`：最高对比度（接近 Windows 高对比度模式）

### 10.2 high-contrast.css

```css
@media (prefers-contrast: more) {
  :root {
    --text: #ffffff;
    --text-secondary: #d0d8e4;
    --text-muted: #a0aab8;
    --border: #4a5870;
    --border-strong: #6a7890;
    --accent: #5b8eff;
    --accent-hover: #7aa3ff;
  }
}

@media (prefers-contrast: high) {
  :root {
    --canvas: #000000;
    --surface: #0a0a0a;
    --surface-raised: #141414;
    --text: #ffffff;
    --text-secondary: #f0f0f0;
    --text-muted: #c0c0c0;
    --border: #808080;
    --border-strong: #c0c0c0;
    --accent: #ffff00;
    --accent-hover: #ffff80;
    --success: #00ff00;
    --warning: #ffff00;
    --danger: #ff0000;
    --shadow-focus: 0 0 0 3px #ffff00;
  }
}
```

- `prefers-contrast: more`：轻微提升对比度，保持深色主题
- `prefers-contrast: high`：使用纯黑底 + 高饱和色，接近 Windows 高对比度模式
- 焦点环在 `high` 下变为黄色 3px 实心环（最大可见性）

### 10.3 不依赖颜色的信息

所有状态色搭配图标或文字：

| 状态 | 颜色 | 图标 / 文字 |
|---|---|---|
| 成功 | `--success`（绿） | ✓ 图标 + "成功"文字 |
| 警告 | `--warning`（黄） | ⚠ 图标 + "警告"文字 |
| 危险 | `--danger`（红） | ✗ 图标 + "失败"文字 |
| 信息 | `--accent`（蓝） | i 图标 + "提示"文字 |
| 启用 | `--success`（绿） | 实心圆点 + "启用"文字 |
| 停用 | `--text-quiet`（灰） | 空心圆点 + "停用"文字 |

### 10.4 Windows 高对比度模式

- Windows 系统级高对比度模式会自动触发 `prefers-contrast: high`
- 应用不强制覆盖系统颜色（用户优先）
- 但保证布局不破：所有元素保留 border，不仅靠背景色区分

---

## 11. 颜色对比度

### 11.1 WCAG AA 标准

| 元素类型 | 对比度要求 | 现状审查 |
|---|---|---|
| 正文文字（< 18px） | ≥ 4.5:1 | `--text`（#eef3f9）on `--canvas`（#070b12）≈ 17:1 ✓ |
| 大文字（≥ 18px 或 14px+ bold） | ≥ 3:1 | `--font-xl` 标题 ✓ |
| 交互元素边框 | ≥ 3:1 | `--border`（#223249）on `--surface`（#0d1420）≈ 1.5:1 ✗ |
| 焦点环 | ≥ 3:1 | `--focus`（#9cbdff）on `--canvas` ≈ 8:1 ✓ |
| 状态图标 | ≥ 3:1 | `--success` / `--warning` / `--danger` on `--surface` 均 ≥ 4:1 ✓ |

### 11.2 已知问题修复

| 问题 | 修复方案 |
|---|---|
| `--text-muted`（#97a6b9）on `--surface`（#0d1420）对比度 ≈ 6:1 | 通过 ✓ |
| `--text-quiet`（#77879d）on `--surface`（#0d1420）对比度 ≈ 4.3:1 | 略低于 4.5:1，**调整**为 `#8294aa`（≈ 5:1） |
| `--border-subtle`（#1a2739）作为分隔线对比度过低 | 仅作视觉分隔，不承载信息；用 `--border` 替代关键分隔 |
| placeholder `--text-muted` on `--surface-raised` | 通过 ✓ |
| 禁用态 opacity 0.45 导致对比度不足 | 禁用态文字对比度不要求（WCAG 豁免），但保留可读性 |

### 11.3 contrast 检查工具

新增 `tests/frontend/contrast-audit.test.cjs`：

- 解析 `tokens.css`，提取所有颜色 primitive
- 计算关键组合（text on canvas、text on surface、border on surface 等）的对比度
- 断言所有文字组合 ≥ 4.5:1，大文字 ≥ 3:1，交互元素 ≥ 3:1
- 对比度算法：WCAG 2.1 relative luminance 公式

---

## 12. 数据模型影响

**无**。

- 不修改 `app/core/job_store.py`
- 不修改 `settings.json` schema
- 不修改 `app/desktop.py` 白名单 API
- 不引入任何后端调用
- `localStorage` 不新增字段（沿用子 spec 6 的快捷键提示 dismissed）

---

## 13. 测试边界

### 13.1 三档分辨率视觉回归

`docs/audits/v0.3.0/` 下为每个关键页面在三档分辨率下截图：

命名规范：`ui-c-<page>-<breakpoint>.png`，breakpoint 取值 `min` / `std` / `wide`。

| 截图 | 内容 |
|---|---|
| `ui-c-batch-min.png` | 批处理页 1040×680 |
| `ui-c-batch-std.png` | 批处理页 1280×820 |
| `ui-c-batch-wide.png` | 批处理页 1920×1080 |
| `ui-c-history-min.png` | 历史页 1040×680（侧边栏折叠） |
| `ui-c-history-std.png` | 历史页 1280×820 |
| `ui-c-history-wide.png` | 历史页 1920×1080（侧边栏展开） |
| `ui-c-settings-min.png` | 设置页 1040×680（单列） |
| `ui-c-settings-std.png` | 设置页 1280×820 |
| `ui-c-settings-wide.png` | 设置页 1920×1080（双列） |
| `ui-c-comparison-min.png` | 对比视图 1040×680（上下堆叠） |
| `ui-c-comparison-std.png` | 对比视图 1280×820（左右并排） |
| `ui-c-high-contrast.png` | 高对比度模式（prefers-contrast: high） |
| `ui-c-reduced-motion.png` | reduced-motion 模式（脉冲徽章静态） |

### 13.2 键盘导航完整性测试

`tests/frontend/keyboard-nav.test.cjs`：

- 每个页面 Tab 顺序验证（按预期顺序遍历所有交互元素）
- Shift+Tab 反向验证
- 焦点可见性验证（`box-shadow` 包含 `--focus`）
- 对话框 focus trap 验证（Tab 不超出对话框）
- Esc 关闭对话框后焦点返回触发元素

### 13.3 可访问性审查

`tests/frontend/a11y-audit.test.cjs`：

- 解析 `app/web/**/*.js` 渲染的 DOM（用 jsdom 模拟）
- 检查每个交互元素（button / a / input / select / textarea）是否有 `aria-label` 或可见文字
- 检查图标按钮（无文字内容的 button）必须有 `aria-label`
- 检查 `role="button"` 的元素同时有 `tabindex="0"`
- 检查 `role="dialog"` 的元素有 `aria-modal="true"` 和 `aria-labelledby`
- 检查 `role="progressbar"` 的元素有 `aria-valuenow` / `aria-valuemin` / `aria-valuemax`
- 检查 `role="tablist"` 的 `tab` 有 `aria-selected`

### 13.4 对比度测试

`tests/frontend/contrast-audit.test.cjs`（见 §11.3）

### 13.5 集成测试

`tests/integration/test_ui_responsive_e2e.py`（`@pytest.mark.slow`）：

- 启动桌面端，模拟三档窗口尺寸
- 验证窄窗口下侧边栏自动折叠
- 验证宽屏下设置页双列布局
- 验证低于最小分辨率时显示建议 toast

### 13.6 不在测试范围内

- 不引入 axe-core / pa11y 等外部 a11y 工具（违反"无新构建链"约束）
- 不做 JAWS / VoiceOver 测试（资源限制，仅测 NVDA）
- 不做性能基准测试（已在子 spec 6 §11 覆盖）

---

## 14. 性能预算

| 指标 | 预算 | 测量方式 |
|---|---|---|
| `responsive.css` 体积 | ≤ 4 KB（gzip 前） | 文件大小 |
| `high-contrast.css` 体积 | ≤ 2 KB（gzip 前） | 文件大小 |
| 窗口 resize 响应延迟 | ≤ 16ms（一帧内） | resize 事件到 state 更新 |
| Tab 导航延迟 | ≤ 50ms | keydown 到焦点切换 |
| NVDA 屏幕阅读器响应 | ≤ 200ms（聚焦到公告） | 手动测试 |
| 现有 P50 2.38s 推理基线 | 不变 | 不修改处理路径 |

---

## 15. 隐私与离线约束

- 不引入任何网络请求（CSP `connect-src 'none'` 不变）
- 不引入任何外网资源
- 不收集用户辅助功能偏好（`prefers-reduced-motion` / `prefers-contrast` 仅由 CSS 媒体查询消费，不上传）
- 不写入诊断包（用户辅助功能设置视为系统级配置，非应用数据）

---

## 16. 风险与未决项

### 16.1 风险

| 风险 | 缓解措施 |
|---|---|
| webview 对 `prefers-contrast` 支持参差 | 降级为仅 `prefers-reduced-motion` 与 Windows 高对比度模式触发 |
| NVDA 公告过多导致骚扰 | 仅关键状态公告（开始 / 完成 / 错误）；进度不公告 |
| 窄窗口下功能可用性下降 | 关键功能（开始 / 暂停 / 取消）始终在命令栏主操作；次要操作进溢出菜单 |
| ARIA 审查遗漏 | 自动化测试（§13.3）+ NVDA 手动测试双轨 |
| 对比度调整影响视觉调性 | 仅调整 `--text-quiet` 一处；其他通过 ✓ |
| 焦点环在深色主题下不够明显 | `--focus`（#9cbdff）对比度 8:1，已足够；high 模式下变黄 |

### 16.2 已决策的开放问题

1. **是否支持低于 1040×680 的分辨率？**
   - 决策：**支持运行但不保证体验**。启动时显示建议 toast。
   - 依据：用户决策（2026-07-29）

2. **是否内置位图图标 @2x / @3x？**
   - 决策：**不内置**。全部走 SVG，自动缩放。
   - 依据：用户决策（2026-07-29）

3. **是否支持触摸屏手势？**
   - 决策：**不支持**。产品定位为桌面端，YAGNI。
   - 依据：用户决策（2026-07-29）

4. **是否测试 JAWS / VoiceOver？**
   - 决策：**不测试**。仅测 NVDA（Windows 主目标）。
   - 依据：用户决策（2026-07-29）

5. **窄窗口下项目选择器是否隐藏？**
   - 决策：**不隐藏**。改为缩略显示（仅项目名），因为项目上下文重要。
   - 依据：用户决策（2026-07-29）

6. **对比视图在窄窗口下是上下堆叠还是仍左右并排？**
   - 决策：**上下堆叠**。原图在上，结果在下，中间滑块水平拖动。
   - 依据：用户决策（2026-07-29）

---

## 17. 后续步骤

本子 spec 经用户 review 通过后：

1. 修正/确认第 16.2 节的开放问题
2. 交接到 writing-plans 制定实现计划
3. 按计划：先扩展 `tokens.css`（断点 + 高对比度色板）→ 写 `responsive.css` → 写 `high-contrast.css` → ARIA 全量补齐 → 三档分辨率视觉证据 → 键盘导航与 a11y 测试
4. 完成后 v0.3.0 全部 7 项子 spec 设计完毕，进入 M8 实现阶段
