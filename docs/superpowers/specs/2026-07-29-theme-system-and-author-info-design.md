# 配色系统升级与关于对话框作者信息更新

**日期**：2026-07-29
**作者**：Fang Dian（方典）<fangdian@tju.edu.cn>
**状态**：待审阅

## 1. 背景与目标

当前应用只有单一深色主题（蓝黑底 `#070b12` + accent 蓝 `#3478f6`）。用户反馈：

1. **配色不够好看**：底色带明显蓝调，与"纯白"无法形成对称的"黑 ↔ 白"切换感
2. **需要白天模式**：长时间在深色环境下工作疲劳，希望跟随系统主题自动切换
3. **关于对话框作者信息缺失**：当前显示"© 2026 消除车牌作者"，需更新为真实作者信息

**目标**：

- 将暗色主题底色从蓝黑 `#070b12` 改为深灰 `#0a0a0a`（近黑，柔和）
- 新增白天主题：纯白底 `#ffffff` + 深蓝 accent
- 通过 CSS `prefers-color-scheme` 媒体查询跟随系统主题，零配置
- 关于对话框显示作者：Fang Dian（方典）<fangdian@tju.edu.cn>

## 2. 设计决策

### 2.1 暗色主题：从蓝黑到深灰

| 用途 | 旧值（蓝黑） | 新值（深灰） | 说明 |
|------|------------|------------|------|
| `--canvas` | `#070b12` | `#0a0a0a` | 主底色，从蓝黑改为近黑深灰 |
| `--canvas-subtle` | `#0a1019` | `#0f0f0f` | 次级底色 |
| `--surface` | `#0d1420` | `#141414` | 卡片面 |
| `--surface-raised` | `#111a28` | `#1a1a1a` | 抬升面（下拉、弹层） |
| `--surface-strong` | `#152031` | `#222222` | 强调面 |
| `--surface-hover` | `#1a2739` | `#262626` | 悬停面 |
| `--border-subtle` | `#1a2739` | `#1f1f1f` | 次级边框 |
| `--border` | `#223249` | `#2a2a2a` | 标准边框 |
| `--border-strong` | `#2d405b` | `#3a3a3a` | 强调边框 |
| `--accent` | `#3478f6` | `#3b82f6` | 主品牌蓝（提亮 1 档以适配深灰底） |
| `--accent-hover` | `#4e8bff` | `#60a5fa` | 悬停蓝 |
| `--accent-soft` | `#102b57` | `#0d2845` | 软强调底 |
| `--accent-border` | `#2e6bd6` | `#1e40af` | 强调边框 |
| `--text` | `#eef3f9` | `#ffffff` | 主文字（纯白） |
| `--text-secondary` | `#b8c4d3` | `#d4d4d4` | 次级文字（中性灰） |
| `--text-muted` | `#97a6b9` | `#a3a3a3` | 弱化文字 |
| `--text-quiet` | `#77879d` | `#737373` | 最弱文字 |
| `--success` | `#3ac89b` | `#22c55e` | 成功绿（标准 Tailwind green-500） |
| `--warning` | `#e9b153` | `#eab308` | 警告黄 |
| `--danger` | `#ef717a` | `#ef4444` | 危险红 |
| `--focus` | `#9cbdff` | `#60a5fa` | 焦点环 |
| `--scrim` | `rgba(4,7,12,.76)` | `rgba(0,0,0,.76)` | 遮罩 |
| `--canvas-overlay` | `rgba(7,11,18,.82)` | `rgba(0,0,0,.82)` | 浮层底 |
| `--floating-surface` | `rgba(13,20,32,.92)` | `rgba(20,20,20,.92)` | 浮动面板 |
| `--index-surface` | `rgba(7,11,18,.78)` | `rgba(0,0,0,.78)` | 索引层 |

**关键变化**：

- 所有底色从中性蓝（带 `#1a2739` 色相）改为纯灰阶（`#0a0a0a` ~ `#3a3a3a`）
- 文字从冷调灰（`#eef3f9` 带蓝）改为纯灰阶（`#ffffff` ~ `#737373`）
- accent 蓝从 `#3478f6` 提亮到 `#3b82f6`，在深灰底上更显眼
- 状态色（success/warning/danger）统一为 Tailwind 标准色值

### 2.2 白天主题：纯白系

通过 `@media (prefers-color-scheme: light)` 覆盖语义 token：

| 用途 | 白天值 | 说明 |
|------|-------|------|
| `--canvas` | `#ffffff` | 纯白主底 |
| `--canvas-subtle` | `#fafafa` | 次级底色（微微压暗） |
| `--surface` | `#fafafa` | 卡片面 |
| `--surface-raised` | `#ffffff` | 抬升面（带投影） |
| `--surface-strong` | `#f5f5f5` | 强调面 |
| `--surface-hover` | `#f5f5f5` | 悬停面 |
| `--border-subtle` | `#e5e7eb` | 次级边框 |
| `--border` | `#d4d4d4` | 标准边框 |
| `--border-strong` | `#a3a3a3` | 强调边框 |
| `--accent` | `#2563eb` | 深蓝（在白底上满足 WCAG AA） |
| `--accent-hover` | `#1d4ed8` | 悬停蓝 |
| `--accent-soft` | `#dbeafe` | 软强调底 |
| `--accent-border` | `#3b82f6` | 强调边框 |
| `--text` | `#000000` | 主文字（纯黑） |
| `--text-secondary` | `#525252` | 次级文字 |
| `--text-muted` | `#737373` | 弱化文字 |
| `--text-quiet` | `#a3a3a3` | 最弱文字 |
| `--success` | `#16a34a` | 成功绿 |
| `--warning` | `#ca8a04` | 警告黄 |
| `--danger` | `#dc2626` | 危险红 |
| `--focus` | `#3b82f6` | 焦点环 |
| `--scrim` | `rgba(0,0,0,.5)` | 遮罩（浅色遮罩透明度更低） |
| `--canvas-overlay` | `rgba(255,255,255,.9)` | 浮层底 |
| `--floating-surface` | `rgba(255,255,255,.95)` | 浮动面板 |
| `--index-surface` | `rgba(255,255,255,.85)` | 索引层 |
| `--shadow-panel` | `0 14px 40px rgba(0,0,0,.08)` | 面板阴影（更轻） |
| `--shadow-drawer` | `-20px 0 45px rgba(0,0,0,.1)` | 抽屉阴影 |

**对称关系**：

- canvas：`#0a0a0a` ↔ `#ffffff`（近黑 ↔ 纯白）
- surface：`#141414` ↔ `#fafafa`（抬亮 ↔ 压暗）
- text：`#ffffff` ↔ `#000000`（纯白 ↔ 纯黑）
- accent：`#3b82f6` 亮蓝 ↔ `#2563eb` 深蓝（在各自底色上都满足 WCAG AA）

### 2.3 主题切换策略：跟随系统

**实现方式**：CSS `prefers-color-scheme` 媒体查询

```css
:root {
  color-scheme: dark light;
  /* 默认暗色主题 tokens */
}

@media (prefers-color-scheme: light) {
  :root {
    /* 白天主题 tokens 覆盖 */
  }
}
```

**优点**：

- 零配置：用户在 Windows 设置里切换"深色/浅色应用模式"，应用自动跟随
- 无需持久化用户偏好（不增加 settings.json 字段）
- 无需 JavaScript 监听和切换
- WebView2 完整支持 `prefers-color-scheme`

**不实现**：

- 应用内手动切换按钮（YAGNI——用户已选择"跟随系统"）
- 主题偏好持久化（YAGNI——跟随系统即不需要存）
- 用户自定义主题（YAGNI）

### 2.4 关于对话框作者信息

修改 `app/web/index.html` 中关于对话框的版权信息：

```html
<p class="about-copyright">© 2026 Fang Dian（方典）. 保留所有权利。</p>
<p class="about-author">作者：Fang Dian（方典）</p>
<p class="about-email">fangdian@tju.edu.cn</p>
```

新增 `.about-author` 和 `.about-email` 样式（居中、中等字号）。

## 3. 影响范围

### 3.1 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `app/web/styles/tokens.css` | 重写所有语义 token 的值，新增 `@media (prefers-color-scheme: light)` 块覆盖白天主题 |
| `app/web/index.html` | 更新关于对话框作者信息 HTML |
| `app/web/styles/history-settings.css` | 新增 `.about-author`、`.about-email` 样式 |
| `docs/user-guide.md` | 新增"主题与配色"章节说明跟随系统行为 |
| `docs/troubleshooting.md` | 新增"主题切换不生效"排查项 |
| `docs/release-checklist.md` | v0.3.0 配色系统升级条目 |
| `RELEASE.md` | 版本说明新增主题系统 |

### 3.2 不需要修改的文件

- **所有组件 CSS**（`base.css`、`components.css`、`batch.css`、`review.css`、`history-settings.css` 的组件部分）：因为它们全部通过 `var(--token)` 引用颜色，token 变了它们自动跟随
- **所有 JavaScript**：不涉及主题逻辑
- **后端 Python**：不涉及主题逻辑
- **测试代码**：现有测试不依赖具体颜色值（CSS 变量引用测试已覆盖）

### 3.3 兼容性

- **WebView2**：完整支持 `prefers-color-scheme`（Evergreen Runtime 90+）
- **旧版浏览器**：不支持时会回退到默认暗色主题，不影响功能
- **PyInstaller 打包**：tokens.css 作为静态资源打包，无影响

## 4. 测试策略

### 4.1 视觉验证

- 在 Windows 系统设置中切换"深色/浅色应用模式"，确认应用自动切换主题
- 检查所有页面（批处理、待复核、任务历史、设置）在两种主题下的可读性
- 检查关于对话框作者信息显示正确

### 4.2 回归测试

- 现有前端测试（CSS 变量引用测试）应全部通过
- 现有后端测试不受影响
- ruff/mypy 不受影响

### 4.3 对比度验证

- 暗色主题：`#ffffff` 文字 on `#0a0a0a` 底 → 对比度 19.3:1（AAA）
- 白天主题：`#000000` 文字 on `#ffffff` 底 → 对比度 21:1（AAA）
- 暗色 accent：`#3b82f6` on `#0a0a0a` → 对比度 4.6:1（AA）
- 白天 accent：`#2563eb` on `#ffffff` → 对比度 5.2:1（AA）

## 5. 实现顺序

1. **修改 tokens.css**：重写暗色 token 值，新增白天主题媒体查询块
2. **更新关于对话框**：修改 index.html 作者信息，新增 about-author/about-email 样式
3. **打包 exe 预览**：用 build_preview.ps1 重新打包
4. **视觉验证**：用户在 Windows 设置中切换主题，确认效果
5. **文档同步**：更新 user-guide、troubleshooting、release-checklist、RELEASE.md

## 6. 不实现（YAGNI）

- 应用内主题切换按钮
- 主题偏好持久化到 settings.json
- 用户自定义主题色
- 主题切换动画
- 主题切换音效
