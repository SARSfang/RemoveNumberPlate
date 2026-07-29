# 子 Spec 5：UI 升级 A — 视觉语言与设计系统

> 日期：2026-07-29
> 状态：待评审
> 所属总纲：[2026-07-29-v0.3.0-master-design.md](./2026-07-29-v0.3.0-master-design.md)
> 推进顺序：第 5 项（共 7 项）
> 依赖：子 spec 1-4 已定信息架构（监视文件夹 / 批量后处理 / 项目预设 / 历史搜索）

---

## 1. 版本与范围

本子 spec 定义 v0.3.0 的视觉语言，更新设计系统，为后续 UI 子 spec（6 信息架构、7 响应性与可访问性）与四个 D 功能的视觉表达定调。

视觉语言目标：从"工具能用"升级到"高端商务感"——克制、精确、可信赖，面向专业摄影师客户交付场景。

**在范围内**：

- `design-system/MASTER.md` 更新（新组件、新动效规范、新 token）
- 设计 token 扩展：间距、圆角、阴影、动效四类 token
- 排版规范：字号梯度、字重、行高
- 微动效规范：150-220ms 过渡、`prefers-reduced-motion` 降级
- 组件视觉规范：按钮、卡片、对话框、输入框、徽章、标签页
- 新增组件视觉：项目选择器、对比视图、筛选条、向导弹出、监视文件夹管理区
- `app/web/styles/tokens.css` 扩展
- `app/web/styles/components.css` 视觉精进
- 视觉证据收集（`docs/audits/v0.3.0/` 截图）

**不在范围内**：

- 信息架构与导航重构（留给子 spec 6）
- 响应式断点、高 DPI、ARIA 审查（留给子 spec 7）
- 任何后端 / 数据模型变更
- 任何新增网络请求

---

## 2. 已确认需求决策

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 视觉调性 | 高端商务感：克制配色、精确排版、低饱和度色彩、深色主题为唯一主题 |
| 2 | 主题策略 | 仅深色主题，不引入浅色主题切换（YAGNI，避免双倍维护） |
| 3 | 动效区间 | 150-220ms 过渡；微动效用 150ms，状态切换用 200ms，复杂过渡用 220ms |
| 4 | 动效降级 | 全量遵守 `prefers-reduced-motion: reduce`，禁用非必要位移与脉冲 |
| 5 | 字体策略 | 沿用系统字体栈（无 CDN，CSP `connect-src 'none'` 不变）；中文字体回退优先 `PingFang SC` / `Microsoft YaHei` |
| 6 | 圆角风格 | 中等圆角（8-12px 主流），不采用 fully-rounded 与 sharp-corner 风格 |
| 7 | 阴影风格 | 低饱和深色阴影 + 偶尔的高光描边模拟高度，不采用强阴影拟物风 |
| 8 | 设计系统文档位置 | `docs/design-system/MASTER.md`（新建文档目录） |
| 9 | 视觉证据位置 | `docs/audits/v0.3.0/`（与总纲 §3.4 一致） |
| 10 | 主色 | 沿用现有 `--blue-600` 为 accent；不引入新主色，仅扩展色板深度 |

---

## 3. 架构概览

### 3.1 实现方案

采用**方案 1：Token 先行 + 文档驱动 + 组件 CSS 精进**。

```
┌─ docs/design-system/ ───────────────────────────────────────┐
│  MASTER.md (新建)                                            │
│    ├─ 设计原则与视觉调性                                     │
│    ├─ Token 全集（间距/圆角/阴影/动效/排版/色彩）            │
│    ├─ 组件视觉规范（按钮/卡片/对话框/...）                   │
│    └─ 微动效规范                                             │
└─────────────────────────────────────────────────────────────┘

┌─ app/web/styles/ ───────────────────────────────────────────┐
│  tokens.css (扩展)                                          │
│    新增：spacing scale / radius scale / shadow scale         │
│    新增：motion duration / easing / typography line-height   │
│  components.css (精进)                                      │
│    重写：按钮 / 卡片 / 对话框 / 输入框 / 徽章 / 标签页        │
│    新增：项目选择器 / 对比视图 / 筛选条 / 向导弹出 / 监视区  │
│  base.css (排版细节)                                        │
│    调整：字号梯度 / 字重 / 行高 / letter-spacing             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 组件职责与依赖方向

- `docs/design-system/MASTER.md`：作为单一真实来源（source of truth），所有 token 与组件规范以此为准
- `tokens.css`：将 MASTER.md 中的 token 落地为 CSS 变量
- `components.css`：消费 token，定义组件视觉；不直接硬编码颜色 / 间距
- 子 spec 6 / 7 依赖本 spec 的 token 与组件视觉规范

**关键设计原则**：Token 是契约，组件 CSS 不绕过 token 直写常量；MASTER.md 与 tokens.css 必须同步。

### 3.3 方案对比（已评估）

| 方案 | 描述 | 评价 |
|---|---|---|
| **方案 1（采纳）** | Token 先行 + 文档驱动 + 组件 CSS 精进 | 沿用现有无框架 CSS 架构；文档化便于跨 spec 对齐 |
| 方案 2 | 引入 Tailwind / UnoCSS | 违反"无 CDN / 无新构建链"约束；现有 CSP 不允许 |
| 方案 3 | 引入 CSS-in-JS | 违反"无框架 / 无构建链"约束 |

---

## 4. 设计 Token 扩展

### 4.1 现有 token 盘点

`app/web/styles/tokens.css` 当前已有：
- 色彩 primitive（ink / slate / blue / green / amber / red）+ semantic
- 间距 `--space-1` 到 `--space-10`（4 / 8 / 12 / 16 / 20 / 24 / 32 / 40px）
- 圆角 `--radius-1` 到 `--radius-4`（5 / 8 / 12 / 16px）
- 字号 `--font-xs` 到 `--font-2xl`（11 / 12 / 14 / 16 / 22 / 30px）
- 动效 `--duration-fast: 120ms` / `--duration-base: 180ms`
- 阴影 `--shadow-panel` / `--shadow-drawer`
- focus ring、component heights

### 4.2 新增 spacing token

补充更细粒度与更大尺度的间距（沿用 4px 基线）：

```css
--space-0: 0px;
--space-px: 1px;       /* 描边与分隔线用 */
--space-1: 4px;        /* 已有 */
--space-2: 8px;        /* 已有 */
--space-3: 12px;       /* 已有 */
--space-4: 16px;       /* 已有 */
--space-5: 20px;       /* 已有 */
--space-6: 24px;       /* 已有 */
--space-8: 32px;       /* 已有 */
--space-10: 40px;      /* 已有 */
--space-12: 48px;      /* 新增：区块大间距 */
--space-16: 64px;      /* 新增：页面纵向呼吸 */
--space-20: 80px;      /* 新增：空状态图与文字间距 */
```

### 4.3 新增 radius token

补充满足组件差异化的圆角档位：

```css
--radius-0: 0px;       /* 直角分隔线 */
--radius-1: 5px;       /* 已有：小控件 */
--radius-2: 8px;       /* 已有：按钮 / 输入框 */
--radius-3: 12px;      /* 已有：面板 / 卡片 */
--radius-4: 16px;      /* 已有：对话框 / 大面板 */
--radius-5: 20px;      /* 新增：超大容器 / 空状态 */
--radius-pill: 999px;  /* 新增：徽章 / 脉冲点 / 圆形按钮 */
```

### 4.4 新增 shadow token

将现有两个阴影扩展为分层阴影系统：

```css
--shadow-xs: 0 1px 2px rgba(0, 0, 0, .24);
--shadow-sm: 0 2px 6px rgba(0, 0, 0, .22);
--shadow-md: 0 6px 18px rgba(0, 0, 0, .24);
--shadow-lg: 0 14px 40px rgba(0, 0, 0, .2);   /* 沿用现有 --shadow-panel */
--shadow-xl: 0 24px 60px rgba(0, 0, 0, .36);
--shadow-drawer: -20px 0 45px rgba(0, 0, 0, .32);  /* 沿用 */
--shadow-focus: 0 0 0 2px var(--canvas), 0 0 0 4px var(--focus);  /* 沿用 --focus-ring */
--shadow-inner: inset 0 1px 0 rgba(255, 255, 255, .04);  /* 新增：高光描边模拟 */
--shadow-inner-strong: inset 0 1px 0 rgba(255, 255, 255, .08);
```

保留旧别名以兼容现有 CSS：

```css
--shadow-panel: var(--shadow-lg);
--focus-ring: var(--shadow-focus);
```

### 4.5 新增 motion token

替换现有 `--duration-fast` / `--duration-base` 为完整动效系统：

```css
/* duration */
--motion-duration-instant: 80ms;   /* 状态切换瞬时反馈 */
--motion-duration-fast: 150ms;     /* 微动效（hover / focus） */
--motion-duration-base: 200ms;     /* 标准过渡（展开 / 折叠） */
--motion-duration-slow: 220ms;     /* 复杂过渡（对话框 / 抽屉） */

/* easing */
--motion-ease-standard: cubic-bezier(0.2, 0, 0, 1);      /* 主力曲线 */
--motion-ease-emphasized: cubic-bezier(0.3, 0, 0, 1);    /* 强调 */
--motion-ease-decelerated: cubic-bezier(0, 0, 0, 1);     /* 入场 */
--motion-ease-accelerated: cubic-bezier(0.3, 0, 1, 1);   /* 出场 */

/* 复合属性快捷引用 */
--motion-fast: var(--motion-duration-fast) var(--motion-ease-standard);
--motion-base: var(--motion-duration-base) var(--motion-ease-standard);
--motion-slow: var(--motion-duration-slow) var(--motion-ease-emphasized);
```

保留旧别名：

```css
--duration-fast: var(--motion-duration-fast);
--duration-base: var(--motion-duration-base);
```

### 4.6 新增 typography token

补齐字重、行高、letter-spacing：

```css
/* 字重 */
--weight-regular: 400;
--weight-medium: 500;
--weight-semibold: 600;
--weight-bold: 700;

/* 行高 */
--leading-tight: 1.2;     /* 标题 */
--leading-snug: 1.35;     /* 副标题 */
--leading-normal: 1.5;    /* 正文 */
--leading-relaxed: 1.65;  /* 长文 / 说明 */

/* letter-spacing */
--tracking-tight: -0.01em;   /* 大标题 */
--tracking-normal: 0;
--tracking-wide: 0.02em;     /* 徽章 / 标签 */
--tracking-wider: 0.08em;    /* 全大写小字 */
```

### 4.7 token 命名规则

- primitive token：`--<类目>-<级别>`（如 `--space-4`、`--blue-600`）
- semantic token：`--<语义>`（如 `--accent`、`--surface`）
- 组件 token：`--<组件>-<属性>`（如 `--button-height`、`--panel-radius`）
- 不允许在组件 CSS 中引用 primitive 色彩 token（必须经过 semantic 间接引用）

---

## 5. 排版规范

### 5.1 字号梯度

| Token | 字号 | 用途 |
|---|---|---|
| `--font-xs` | 11px | 徽章 / 时间戳 / 辅助标签 |
| `--font-sm` | 12px | 表单 secondary、表格次级、说明文字 |
| `--font-md` | 14px | **基准正文**：按钮、输入框、表格主列 |
| `--font-lg` | 16px | 区块小标题、对话框标题 |
| `--font-xl` | 22px | 页面主标题、空状态主文案 |
| `--font-2xl` | 30px | 启动屏 / 关于页大标题 |

### 5.2 字重与行高搭配

| 用途 | 字号 | 字重 | 行高 | letter-spacing |
|---|---|---|---|---|
| 页面主标题 | 22px | 600 | 1.2 | -0.01em |
| 区块标题 | 16px | 600 | 1.35 | 0 |
| 正文 | 14px | 400 | 1.5 | 0 |
| 辅助说明 | 12px | 400 | 1.5 | 0 |
| 徽章 / 标签 | 11px | 500 | 1.2 | 0.02em |
| 全大写小字（如"步骤 02"） | 11px | 600 | 1.2 | 0.08em |

### 5.3 字体栈

沿用现有 `base.css` 中的字体栈，统一明确为：

```css
--font-sans: "PingFang SC", "Microsoft YaHei", -apple-system,
             BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
--font-mono: "JetBrains Mono", "Cascadia Code", Consolas,
             "SF Mono", Menlo, monospace;
```

- 默认正文走 `--font-sans`
- 路径、ID、计数等代码场景走 `--font-mono`
- 不引入任何外网字体（CSP `connect-src 'none'` 不变）

### 5.4 中文排版细节

- 中英文混排在 `base.css` 中通过 `font-feature-settings: "tnum"` 启用等宽数字
- 标点挤压：CSS `text-spacing-trim: space-all` （兼容浏览器降级为默认）
- 长文本截断统一用 `text-overflow: ellipsis` + `overflow: hidden`

---

## 6. 微动效规范

### 6.1 时长区间

| 场景 | 时长 | 曲线 |
|---|---|---|
| hover / focus 反馈 | 150ms | `--motion-ease-standard` |
| 按钮 press 反馈 | 80ms | `--motion-ease-standard` |
| 面板展开 / 折叠 | 200ms | `--motion-ease-standard` |
| 对话框淡入 | 220ms | `--motion-ease-decelerated` |
| 对话框淡出 | 150ms | `--motion-ease-accelerated` |
| 抽屉滑入 | 220ms | `--motion-ease-emphasized` |
| toast 出现 | 200ms | `--motion-ease-decelerated` |
| toast 消失 | 150ms | `--motion-ease-accelerated` |
| 脉冲徽章循环 | 1200ms（呼吸） | linear |

### 6.2 prefers-reduced-motion 降级

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

- 所有非必要位移、脉冲、滑入动效全部禁用
- 颜色 / 透明度切换保留极短过渡（80ms 以下视为瞬时）
- 脉冲徽章降级为静态彩色点

### 6.3 高端商务感的动效原则

- **不使用 bounce / elastic / back 曲线**（过度活泼不符合商务调性）
- **不使用大位移**（位移 ≤ 8px，避免视觉跳跃）
- **优先用透明度与色彩变化**而非位移
- **不使用旋转动画**（除加载 spinner）

### 6.4 加载与进度动效

- 加载圈：CSS `conic-gradient` + 旋转，2.2s 一圈
- 进度条：宽度过渡 200ms，颜色随进度变化（0-60% 蓝、60-99% 绿、100% 绿稳态）
- 启动扫描：用 `--motion-ease-standard` 200ms 的进度条增长

---

## 7. 组件视觉规范

### 7.1 按钮

| 类型 | 高度 | 内边距 | 圆角 | 字号 | 字重 |
|---|---|---|---|---|---|
| Primary | 40px | 0 16px | 8px | 14px | 600 |
| Secondary | 40px | 0 16px | 8px | 14px | 500 |
| Ghost | 40px | 0 12px | 8px | 14px | 500 |
| Compact | 32px | 0 12px | 6px | 13px | 500 |
| Icon-only | 32px×32px | 0 | 6px | — | — |

- Primary：`background: var(--accent)`、`color: var(--white)`、hover `--accent-hover`
- Secondary：`background: var(--surface-raised)`、border 1px `--border`、hover `--surface-hover`
- Ghost：透明背景、hover 出 `--surface-hover` 底色
- 禁用态：opacity 0.45，cursor `not-allowed`，不响应 hover
- focus 必须可见：使用 `--shadow-focus`，不依赖 `outline: none`
- 所有按钮过渡：`background-color var(--motion-fast), color var(--motion-fast), border-color var(--motion-fast)`

### 7.2 卡片

```
背景: var(--surface)
圆角: var(--radius-3) (12px)
边框: 1px solid var(--border-subtle)
阴影: var(--shadow-md)
内边距: var(--space-5) (20px)
```

- 卡片间距：`var(--space-4)` (16px)
- 卡片标题区：底部 1px `--border-subtle` 分隔，padding 16px 20px
- 卡片主体：padding 20px
- hover 态：阴影升至 `--shadow-lg`，边框变 `--border`

### 7.3 对话框

```
背景: var(--surface)
圆角: var(--radius-4) (16px)
阴影: var(--shadow-xl)
遮罩: var(--scrim)
最大宽度: 480px（默认）/ 640px（宽）
入场: opacity 0→1 + translateY(8px→0)，220ms decelerated
```

- 标题区：字号 16px / 字重 600 / 行高 1.35
- 内容区：字号 14px / 字重 400 / 行高 1.5
- 操作区：右上角对齐主操作按钮，左下角对齐取消
- Esc 关闭时使用 150ms 加速淡出

### 7.4 输入框

| 属性 | 值 |
|---|---|
| 高度 | 40px（标准）/ 32px（compact） |
| 内边距 | 0 12px |
| 圆角 | 8px |
| 背景 | `var(--surface-raised)` |
| 边框 | 1px `var(--border)`；focus 时 1px `var(--accent-border)` + `--shadow-focus` |
| 字号 | 14px |
| placeholder | `var(--text-muted)` |

- 错误态：边框 `var(--danger-border)`、底色 `var(--danger-surface)`
- 禁用态：opacity 0.5
- 文本输入过渡：border-color `var(--motion-fast)`

### 7.5 徽章（Badge）

```
高度: 22px
内边距: 0 8px
圆角: var(--radius-pill) (999px)
字号: 11px
字重: 500
letter-spacing: 0.02em
```

- 状态色：success / warning / danger / info，分别对应 semantic 色
- 软底色版本：`*-soft` 系列（如 `--warning-soft` 底 + `--warning-text` 文字）
- 脉冲徽章：左侧 8px 圆点 + 文字，圆点用 `animation: pulse 1.2s linear infinite`
- `prefers-reduced-motion` 时圆点降级为静态彩色点

### 7.6 标签页（Tabs）

- 标签栏高度：40px
- 选中态：底部 2px `--accent` 指示条
- 未选中态：底部 2px 透明
- 指示条过渡：`transform translateX()` 200ms `--motion-ease-standard`，避免宽度变化导致 reflow
- 字号 14px / 字重 500（未选中）/ 600（选中）
- 焦点态：标签整体 `--shadow-focus`

---

## 8. 新组件视觉规范（针对四个 D 功能）

### 8.1 项目选择器（子 spec 3 用）

批处理页顶部新增"当前项目"下拉选择器：

```
[📁 客户A · 商拍 2026-07  ▾]
```

- 高度 40px、圆角 8px、底色 `--surface-raised`
- 展开下拉后：宽度 320px、最大高度 360px 滚动
- 每个项目行：项目名（14px / 500）+ 客户名（12px / `--text-muted`）
- 当前项目高亮：底色 `--accent-soft` + 左侧 2px `--accent` 竖条
- "管理项目"链接位于下拉底部，跳转设置页

### 8.2 对比视图（子 spec 4 用）

`ComparisonView` 组件的视觉规范：

- 左右并排：中间 1px `--border-subtle` 分隔线
- 滑块手柄：44px×44px 圆形、底色 `--surface-strong`、border 1px `--border`、阴影 `--shadow-md`
- 滑块拖动：cursor `ew-resize`，过渡无（实时跟随）
- 差分高亮模式：差异像素用 `--danger` 半透明叠加（alpha 0.3）
- 标签：左上"原图"、右上"结果"，11px / `--text-muted` / letter-spacing 0.08em

### 8.3 筛选条（子 spec 4 用）

历史页顶部筛选条：

```
[状态 ▾] [日期 ▾] [项目 ▾] [搜索: ___________] [清除]
```

- 整体高度 44px、底色 `--surface`、底部 1px `--border-subtle`
- 筛选项：高度 32px、圆角 6px、底色 `--surface-raised`、字间距 0.02em
- 搜索框：内嵌放大镜图标，宽度自适应
- "清除"按钮：Ghost 风格，仅在任一筛选激活时出现

### 8.4 向导弹出（子 spec 2 用）

批量后处理配置的向导弹出：

- 三步：命名模板 → 水印 → EXIF
- 顶部步骤指示器：三个圆点 + 连接线，当前步骤用 `--accent` 实心，已完成用 `--success`，未达用 `--border`
- 圆点直径 24px，字号 11px / 600 / `--text-on-accent`
- 步骤切换：内容区淡入 200ms
- 底部操作区：左"上一步"、右"下一步 / 完成"

### 8.5 监视文件夹管理区（子 spec 1 用）

设置页第 4 区块视觉：

- 区块标题沿用现有"02 ·"前缀风格（11px / 600 / `--text-muted` / tracking 0.08em）
- 文件夹列表：每行高度 56px、底色 `--surface`、底部 1px `--border-subtle`
- 启用状态指示：左侧 8px 圆点，启用 `--success`，停用 `--text-quiet`
- 路径文字：`--font-mono` 13px、长路径 ellipsis、hover tooltip 显示完整
- 启停 / 移除按钮：Compact Ghost，移除按钮 hover 时变 `--danger-text`

---

## 9. design-system/MASTER.md 结构

新建 `docs/design-system/MASTER.md`，结构如下：

```markdown
# 设计系统主控文档

## 1. 设计原则
  - 克制、精确、可信赖
  - 商务优先，工具感而非消费品感
  - 深色主题为唯一主题

## 2. 色彩
  - Primitive 色板
  - Semantic 色彩映射
  - 状态色（success / warning / danger / info）

## 3. 间距
  - 4px 基线
  - spacing scale 0 / px / 1 / 2 / 3 / 4 / 5 / 6 / 8 / 10 / 12 / 16 / 20

## 4. 圆角
  - radius scale 0 / 1 / 2 / 3 / 4 / 5 / pill

## 5. 阴影
  - shadow scale xs / sm / md / lg / xl / drawer / focus / inner

## 6. 排版
  - 字号梯度
  - 字重
  - 行高
  - letter-spacing
  - 字体栈

## 7. 动效
  - duration
  - easing
  - prefers-reduced-motion 降级

## 8. 组件视觉规范
  - 按钮
  - 卡片
  - 对话框
  - 输入框
  - 徽章
  - 标签页
  - 项目选择器
  - 对比视图
  - 筛选条
  - 向导弹出
  - 监视文件夹管理区

## 9. Token 命名规则

## 10. 维护与同步
  - MASTER.md 与 tokens.css 双向同步责任人
  - 任何 token 变更必须同时更新两处
```

---

## 10. 数据模型影响

**无**（纯前端 + 文档）。

- 不修改 `app/core/job_store.py`
- 不修改 `settings.json` schema
- 不修改 `app/desktop.py` 白名单 API
- 不引入任何后端调用

---

## 11. 测试边界

### 11.1 视觉证据

在 `docs/audits/v0.3.0/` 下收集截图，命名为 `ui-a-<场景>.png`：

| 截图 | 内容 |
|---|---|
| `ui-a-buttons-states.png` | 按钮所有类型 × 所有状态（normal / hover / focus / disabled） |
| `ui-a-card.png` | 卡片静态 + hover |
| `ui-a-dialog.png` | 对话框入场瞬间 + 稳态 |
| `ui-a-inputs-states.png` | 输入框 normal / focus / error / disabled |
| `ui-a-badges.png` | 徽章所有状态色 + 脉冲徽章静态截图 |
| `ui-a-tabs.png` | 标签页指示条过渡中间帧 |
| `ui-a-project-selector.png` | 项目选择器展开态 |
| `ui-a-comparison-view.png` | 对比视图滑块在 50% 位置 |
| `ui-a-filter-bar.png` | 历史页筛选条全展开 |
| `ui-a-wizard-popover.png` | 向导第二步水印配置 |
| `ui-a-watch-folder-section.png` | 设置页监视文件夹管理区 |

### 11.2 设计 token 一致性检查

新增 `tests/frontend/tokens-consistency.test.cjs`（`node --test` 模式）：

- 解析 `tokens.css`，提取所有 `--<token>:` 定义
- 解析 `MASTER.md`，提取所有 fenced code block 中的 `--<token>:` 定义
- 断言两处 token 名称集合一致
- 断言每个 token 的值一致（允许别名引用差异）
- 断言 `components.css` 不直接硬编码颜色 hex / rgb（仅允许 `--<token>` 或 `rgba(var(--xxx), .5)` 形式）

### 11.3 组件 CSS 单元测试

- `tests/frontend/components-visual.test.cjs`：
  - 检查 `.button-primary`、`.card`、`.dialog`、`.input`、`.badge`、`.tab` 等关键类名在 `components.css` 中存在
  - 检查这些类引用的 token 均在 `tokens.css` 中已定义
  - 不直接断言渲染像素（pixel diff 留给子 spec 7 的视觉回归）

### 11.4 不在测试范围内

- 不引入 Playwright / Puppeteer（违反"无新构建链"约束）
- 不做像素级视觉回归（留给子 spec 7）
- 不做屏幕阅读器测试（留给子 spec 7）

---

## 12. 性能预算

| 指标 | 预算 | 测量方式 |
|---|---|---|
| `tokens.css` 体积 | ≤ 6 KB（gzip 前） | 文件大小 |
| `components.css` 体积 | ≤ 24 KB（gzip 前） | 文件大小 |
| `base.css` 体积 | ≤ 8 KB（gzip 前） | 文件大小 |
| CSS 解析阻塞 | 不增加（沿用现有 `<link>` 同步加载策略） | DevTools Performance |
| 现有 P50 2.38s 推理基线 | 不变 | 不引入 JS / DOM 改动到处理路径 |

---

## 13. 隐私与离线约束

- 不引入任何网络请求（CSP `connect-src 'none'` 不变）
- 不引入任何外网字体或图标 CDN
- 图标全部使用内联 SVG 或 SVG sprite（沿用现有 `app/web/assets/` 模式）
- `MASTER.md` 文档不包含任何用户数据示例

---

## 14. 风险与未决项

### 14.1 风险

| 风险 | 缓解措施 |
|---|---|
| 视觉变更波及现有页面布局 | 仅扩展 token，不重写已有布局结构；现有 `--space-*` / `--radius-*` / `--duration-*` 别名保留 |
| 组件 CSS 精进引入视觉回归 | 视觉证据截图对比 v0.2.0-rc.7 基线；任何布局位移回滚 |
| MASTER.md 与 tokens.css 漂移 | 一致性测试（§11.2）在 CI 中阻断 |
| 微动效在低端 GPU 上卡顿 | 所有动效仅 opacity / transform / color，不触发 layout / paint 重负载 |
| 中文字体回退在不同 Windows 版本表现不一 | 字体栈优先 `PingFang SC`（Win10+ 默认）→ `Microsoft YaHei` 兜底 |

### 14.2 已决策的开放问题

1. **是否引入浅色主题？**
   - 决策：**不引入**。仅深色主题，避免双倍维护成本。
   - 依据：用户决策（2026-07-29）

2. **是否引入新的主色（如靛蓝 / 紫色作为商务强调色）？**
   - 决策：**不引入**。沿用 `--blue-600`，仅扩展色板深度。
   - 依据：用户决策（2026-07-29）

3. **设计系统文档是否独立成目录？**
   - 决策：**独立**。新建 `docs/design-system/MASTER.md`。
   - 依据：用户决策（2026-07-29）

4. **是否引入图标字体（如 Font Awesome）？**
   - 决策：**不引入**。所有图标走内联 SVG。
   - 依据：CSP 与离线约束

---

## 15. 后续步骤

本子 spec 经用户 review 通过后：

1. 修正/确认第 14.2 节的开放问题
2. 交接到 writing-plans 制定实现计划
3. 按计划：先扩展 `tokens.css` → 写 `MASTER.md` → 精进 `components.css` → 收集视觉证据
4. 完成后进入子 spec 6（UI 升级 B：信息架构与交互模式）
