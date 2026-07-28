# 桌面版预览优先工作台实施计划

**日期：** 2026-07-28

**状态：** 等待用户批准

**对应规格：** [桌面版预览优先工作台设计规格](../specs/2026-07-28-desktop-preview-workspace-design.md)

**视觉目标：** [方案 2：底部胶片带 + 大幅单图预览](../../design/desktop-preview-workspace-option-2.png)

**目标版本：** `v0.2.0-rc.5`

## 1. 实施原则

1. 保持 WebView2、Python 和原生 HTML/CSS/JavaScript，不引入前端运行时框架或打包器。
2. 先建立任务/预览后端契约，再迁移前端；任何阶段都保持主分支可测试。
3. 用多个 `defer` 经典脚本和 `window.PlateApp` 命名空间拆分逻辑，不使用 ES Modules。
4. 新预览接口只接受任务 ID，不接受前端传入的文件路径。
5. UI 预览失败不能影响 AI 批处理。
6. 视觉稿是布局与质感基准，功能以批准规格为准。
7. 每个里程碑完成后运行定向测试；每个可独立回滚的里程碑单独提交。
8. 不修改检测器、LaMa、遮罩扩边、输出质量或模型文件。
9. 发现现有工作树出现不属于本计划的更改时停止覆盖并先核对。
10. 全部处理与预览继续在本机离线完成；不接入付费 API、云推理、订阅服务或需要用户另行购买的运行时。

## 2. 完成定义

只有以下证据全部成立，任务才算完成：

- 后端预览接口、任务清单事件和安全测试通过。
- 批处理页实现空状态、主预览、原图/结果、跟随/固定、胶片带、信息栏和确认对话框。
- 待复核、历史和设置使用统一设计系统。
- 1040×680、常用大窗口和 200% 缩放可完成核心任务。
- 键盘、焦点、状态播报、减少动态效果和对比度检查通过。
- 100 张任务的胶片带和缓存上限验证通过。
- RC4 固定样片基线相比，启用预览后的处理中位耗时增加不超过 5%。
- Python 单元、集成、模型、WebView2 烟雾和发行检查全部通过。
- 实现截图与选定视觉稿完成同视口对照；照片占比、导航/命令栏高度、胶片带节奏、信息栏宽度、字体层级和主操作层级逐项验收。
- `v0.2.0-rc.5` 安装包构建并在干净 Windows 环境完成安装/启动/卸载烟雾测试。
- Git 工作树干净，提交记录与最终证据文档齐全。

## 3. 里程碑与提交边界

| 里程碑 | 结果 | 提交 |
|---|---|---|
| M0 | 基线与测试入口 | `test: lock preview workspace baseline` |
| M1 | 任务清单与安全预览服务 | `feat: add bounded job preview service` |
| M2 | Python 桥接契约 | `feat: expose preview workspace bridge` |
| M3 | 前端模块与设计变量 | `refactor: split desktop frontend modules` |
| M4 | 预览优先批处理页 | `feat: build preview-first batch workspace` |
| M5 | 胶片带性能与键盘 | `feat: add virtualized batch filmstrip` |
| M6 | 复核、历史与设置统一 | `feat: unify desktop workspaces` |
| M7 | 无障碍、视觉与性能 QA | `test: verify desktop workspace experience` |
| M8 | 文档、版本和 RC5 | `release: prepare v0.2.0 rc5 desktop workspace` |

## 4. M0：锁定基线

### 4.1 检查工作树与版本

**读取：**

- `app/version.py`
- `pyproject.toml`
- `requirements-dev.txt`
- `.github/workflows/quality.yml`
- `packaging/build_release.ps1`

**执行：**

```powershell
git status --short
python -m pytest tests/unit -q
python -m ruff check app scripts tests
python -m mypy app scripts
```

**通过条件：**

- 工作树仅包含本计划明确产生的更改。
- RC4 单元测试、lint 和类型检查为绿色。
- 将测试数量和耗时记录到实施证据文档。

### 4.2 建立性能基线

**读取：**

- `scripts/benchmark_end_to_end.py`
- `tests/unit/test_benchmark_end_to_end_script.py`
- `docs/performance.md`

**操作：**

1. 建立本地且已被 Git 忽略的 `testdata/private/perf-rc5-inputs/`，其中必须恰好包含 10 张用户自有样片；不联网下载、不上传、不产生第三方费用。
2. 在证据文档中记录 10 个文件的文件名、字节数和 SHA-256；后续 RC5 复测必须使用相同清单与顺序，清单不一致即停止比较。
3. 预热模型一次。
4. 运行至少 3 轮，记录每张处理耗时中位数和进程峰值内存。
5. 记录 RC4 基线，不把首次模型加载计入单张中位数。

**输出：**

- 在最终证据文档中记录机器、样片清单、命令和结果；文档只记录哈希与元数据，不嵌入照片。
- 不把私人照片提交到 Git。

### 4.3 保存当前视觉基线

已有审查截图：

- `docs/audits/2026-07-28-desktop-ui/01-batch-empty.png`
- `docs/audits/2026-07-28-desktop-ui/02-review-empty.png`
- `docs/audits/2026-07-28-desktop-ui/03-history-empty.png`
- `docs/audits/2026-07-28-desktop-ui/04-settings.png`

确认这些截图与 RC4 当前代码一致。若不一致，重新截图并单独说明原因。

## 5. M1：任务清单与安全预览服务

### 5.1 创建预览领域服务

**新增：**

- `app/core/job_preview.py`
- `tests/unit/test_job_preview.py`

**先写失败测试：**

1. 原图预览最长边不超过 1800×1200 边界。
2. 缩略图不超过 320×220 边界。
3. 原图预览 JPEG 质量参数固定为 88。
4. 缩略图 JPEG 质量参数固定为 72。
5. EXIF 方向只归一化一次。
6. 返回原始宽高和实际预览宽高。
7. 未完成任务请求结果时返回不可用，不伪造图片。
8. 输出文件缺失时返回结构化不可用原因。
9. 源文件缺失时返回结构化不可用原因。
10. 非 `original/result` variant 被拒绝。

**实现对象：**

```text
PreviewKind
PreviewUnavailableReason
JobPreview
encode_preview(path, bounds, quality)
build_job_preview(job, kind)
```

图像编码复用 `app/core/image_io.py` 的方向处理逻辑，禁止复制一套不一致的 EXIF 规则。

**验证：**

```powershell
python -m pytest tests/unit/test_job_preview.py -q
python -m ruff check app/core/job_preview.py tests/unit/test_job_preview.py
python -m mypy app/core
```

### 5.2 调整批次任务创建顺序

**修改：**

- `app/desktop.py`
- `tests/unit/test_desktop.py`

**先写失败测试：**

1. `batch_items_ready` 在第一个 `item_started` 之前发送。
2. 事件项目顺序与 `discover_images` 一致。
3. 每个项目只包含任务 ID、名称、序号和初始状态，不包含完整文件路径。
4. 模型首次加载失败时，本批仍排队任务全部转为失败。
5. 模型失败事件包含可恢复说明，不留下永久 queued 状态。
6. 取消发生在两张之间时，尚未开始的任务全部转为 cancelled。

**实现顺序：**

1. 图片发现。
2. 存储预检。
3. 创建全部任务记录。
4. 发送 `batch_items_ready`。
5. 首次创建处理器。
6. 按现有串行顺序处理。

**验证：**

```powershell
python -m pytest tests/unit/test_desktop.py -q
python -m pytest tests/unit/test_job_store.py tests/unit/test_batch.py -q
```

## 6. M2：Python 桥接契约

### 6.1 增加任务 ID 预览 API

**修改：**

- `app/desktop.py`
- `tests/unit/test_desktop.py`

**新增允许列表方法：**

```text
get_job_thumbnail(identifier)
get_job_preview(identifier, variant)
open_job_output(identifier)
```

**先写失败测试：**

1. 未知任务 ID 返回结构化不可用结果。
2. 前端不能通过 identifier 注入路径。
3. 原图与结果都从 `JobStore` 解析。
4. `open_job_output` 只打开应用输出目录。
5. 输出目录以外的任务输出被拒绝。
6. 预览方法不修改任务状态。
7. 预览异常被转换成安全消息，不把本机路径暴露给界面错误文本。

**响应字段：**

```json
{
  "available": true,
  "image": "data:image/jpeg;base64,...",
  "width": 6000,
  "height": 4000,
  "preview_width": 1800,
  "preview_height": 1200,
  "variant": "result",
  "message": ""
}
```

### 6.2 扩展历史描述

**修改：**

- `app/desktop.py`
- `tests/unit/test_desktop.py`

`list_history` 增加前端详情需要、但不泄露路径的字段：

- `detection_count`
- `risks`
- `source_available`
- `output_available`

完整路径只保留在 Python 内部。

### 6.3 兼容现有界面

迁移期间保留现有 `open_output(value)`，直到新批处理、历史和复核全部改用任务 ID。最终删除前必须证明所有前端调用点已迁移，并更新测试。

**验证：**

```powershell
python -m pytest tests/unit/test_desktop.py tests/unit/test_job_preview.py -q
python -m ruff check app tests
python -m mypy app scripts
```

## 7. M3：前端模块与设计变量

### 7.1 建立无框架模块骨架

**新增：**

- `app/web/core/state.js`
- `app/web/core/bridge.js`
- `app/web/core/shortcuts.js`
- `app/web/components/dialog.js`
- `app/web/components/toast.js`
- `app/web/batch/workspace.js`
- `app/web/batch/preview.js`
- `app/web/batch/filmstrip.js`
- `app/web/review/editor.js`
- `app/web/history/history.js`
- `app/web/settings/settings.js`

**修改：**

- `app/web/index.html`
- `app/web/app.js`

所有文件：

- 使用 IIFE。
- 只在 `window.PlateApp` 下导出。
- 通过 `defer` 按依赖顺序加载。
- 不引入模块加载器或 npm 运行时。

### 7.2 建立纯状态测试

**新增：**

- `tests/frontend/state.test.cjs`
- `tests/frontend/bridge-events.test.cjs`

`state.js` 同时支持浏览器全局和 CommonJS 测试导出，不依赖 DOM。

**修改：**

- `.github/workflows/quality.yml`

在 CI 显式使用：

```yaml
- uses: actions/setup-node@v4
  with:
    node-version: "22"
- run: node --test tests/frontend/*.test.cjs
```

**测试状态：**

- following 收到 `item_started`
- pinned 不被后台抢走
- restore following
- completed 后结果可用
- result 不可用时回退 original
- paused/resumed/cancelled/finished
- preview error 不改变 job status

### 7.3 拆分 CSS

**新增：**

- `app/web/styles/tokens.css`
- `app/web/styles/base.css`
- `app/web/styles/components.css`
- `app/web/styles/batch.css`
- `app/web/styles/review.css`
- `app/web/styles/history-settings.css`

**迁移：**

- `app/web/styles.css`

顺序：

1. 把原始颜色、间距、字号、圆角、时长放入 primitive 区。
2. 建立 semantic 区。
3. 建立 component 区。
4. 逐组件替换硬编码值。
5. 所有页面迁移后删除旧 `styles.css`。

**静态检查：**

- 组件文件不得新增散落的重复主色、状态色和间距值。
- `prefers-reduced-motion` 保留。
- 焦点样式在新 CSS 中唯一且一致。

### 7.4 保持启动烟雾测试

**修改：**

- `tests/unit/test_desktop.py` 或现有 WebView2 烟雾测试

证明：

- 所有新脚本和样式能从发行资源路径加载。
- `frontend_ready()` 正常调用。
- 任何单个脚本语法错误都会使烟雾测试失败。

## 8. M4：预览优先批处理页

### 8.1 重写批处理 HTML

**修改：**

- `app/web/index.html`
- `app/web/styles/batch.css`
- `app/web/batch/workspace.js`

**空状态：**

- 画布即拖放区。
- 选择照片/文件夹。
- 完全离线提示。
- 无统计卡和空表。

**运行状态：**

- 顶部命令栏。
- 中央单图画布。
- 右侧信息栏。
- 底部胶片带。

### 8.2 批次命令栏

实现：

- “本次处理 · N 张”
- 完成数/总数与百分比
- 整体进度
- 暂停/继续
- 取消剩余
- 添加照片
- 进入待复核

规则：

- 运行或暂停时禁用添加照片。
- 无待复核项时禁用进入复核。
- 取消通过确认对话框。
- 对话框 Esc 关闭、焦点锁定并回到触发按钮。

### 8.3 主预览

**修改：**

- `app/web/batch/preview.js`
- `app/web/styles/batch.css`

实现：

- 原图/处理结果标签。
- 可用/处理中/不可用标签状态。
- 适应窗口、1:1、放大、缩小和拖动画布。
- 跟随处理中/已固定。
- 恢复跟随。
- 300ms 骨架阈值。
- 加载失败重试。
- 主预览 LRU 上限 6。

**单元/状态测试：**

- 用户最近选择结果标签，切换到未完成项时回退原图。
- following 的任务完成时自动显示结果。
- pinned 的任务完成不改变选择。
- 缓存淘汰顺序与上限。

### 8.4 右侧信息栏

实现：

- 文件名、尺寸、状态、耗时、风险、输出。
- 打开输出、进入复核、手动标记、重新处理。
- 小于 1180px 时折叠为右侧详情抽屉。
- 抽屉支持 Esc、焦点锁定和焦点归还。

## 9. M5：胶片带性能与键盘

### 9.1 胶片项

**修改：**

- `app/web/batch/filmstrip.js`
- `app/web/styles/batch.css`

实现：

- 固定比例缩略图和占位。
- 文件名和状态。
- 当前处理/当前预览独立标记。
- 点击后固定。
- 完整文件名提示。
- 可见项缩略图懒加载。
- 缩略图缓存上限 64。

### 9.2 窗口化

任务数小于 40 时渲染全部项目；达到 40 时只保留：

- 可见项目
- 前后至少一屏缓冲
- 两端占位宽度

滚动、选择和自动定位不能因为 DOM 回收丢失焦点。

### 9.3 键盘

**修改：**

- `app/web/core/shortcuts.js`
- `app/web/batch/filmstrip.js`

实现：

- Ctrl+O 添加照片。
- 左右浏览。
- Home/End。
- 1/2 切换原图/结果。
- F 恢复跟随。

限制：

- 对话框、输入框、选择框和复核画布焦点下不触发普通快捷键。
- 快捷键不阻止浏览器或系统必须保留的组合。

### 9.4 性能验证

使用生成的 100、500 项任务描述进行前端压力测试：

- DOM 数量受限。
- 选中项在滚动、DOM 回收与自动定位后保持同一任务 ID，且胶片带滚动位置不出现反向跳转。
- 单状态更新不重建整条胶片带。
- 缓存不超过规格上限。
- 切换预览立即显示占位。

## 10. M6：统一复核、历史和设置

### 10.1 复核编辑器

**迁移：**

- 从旧 `app/web/app.js` 迁入 `app/web/review/editor.js`

**修改：**

- `app/web/index.html`
- `app/web/styles/review.css`

保留现有坐标、撤销/重做和重修行为，只调整组织：

- 工具按标记、历史、视图和参数分组。
- 画笔大小只在画笔激活时显示。
- 增加遮罩显示与透明度。
- 确认并重修为唯一主按钮。
- 重修失败保留编辑。
- 复核完成后自动进入下一张。

**回归：**

```powershell
python -m pytest tests/unit/test_manual_mask.py tests/unit/test_desktop.py -q
```

用 `tests/frontend/review_preview.html` 更新视觉夹具，验证画笔、矩形、擦除、删除自动框、缩放和拖动。

### 10.2 任务历史

**修改：**

- `app/web/history/history.js`
- `app/web/styles/history-settings.css`
- `app/web/index.html`

实现：

- 删除两张大说明卡。
- 总数、状态筛选、文件名搜索、刷新、隐私短提示。
- 任务列表成为主内容。
- 选择行后复用预览详情。
- 所有操作改用任务 ID。

筛选与搜索仅作用于已载入的最多 100 条历史；不在本轮增加数据库全文搜索。

### 10.3 设置

**修改：**

- `app/web/settings/settings.js`
- `app/web/styles/history-settings.css`
- `app/web/index.html`

实现：

- 处理
- 性能
- 数据与支持
- 可折叠运行环境详情
- 设置保存后的内联/Toast 反馈

模型、WebView2 和运行时信息为只读，不伪装成禁用表单。

## 11. M7：图标、无障碍、视觉和性能 QA

### 11.1 本地图标

**新增：**

- `app/web/assets/icons/` 下的批准 Lucide 子集
- `THIRD_PARTY_NOTICES.md` 中的 Lucide 许可说明

只包含实际使用的 SVG 文件。不得手工绘制近似图标，不得使用 emoji 或 CSS 图形替代。

检查：

- 统一 `viewBox`
- 统一描边风格
- 图标尺寸由设计变量控制
- 图标按钮有 `aria-label` 和 tooltip

### 11.2 对比度与焦点

检查所有语义颜色组合：

- 正文至少 4.5:1。
- 大文字和 UI 图形至少 3:1。
- 主色、成功、警告和危险在各自表面可辨。
- 键盘焦点在画布、表面和选中项上都清楚。

将检查结果记录在最终证据文档。

### 11.3 键盘和状态播报

走通：

1. 启动。
2. 添加照片。
3. 暂停/继续。
4. 浏览胶片带。
5. 原图/结果。
6. 固定/恢复跟随。
7. 打开详情抽屉。
8. 取消确认。
9. 进入复核。
10. 历史筛选。
11. 设置。

检查：

- Tab 顺序符合视觉顺序。
- 对话框焦点锁定与归还。
- Toast 不抢焦点。
- `aria-live` 不重复轰炸单张细节。

### 11.4 视口

验证：

- 1040×680。
- 1280×800。
- 1440×900 或更大。
- 200% 缩放下等效窄内容宽度。

所有状态必须无水平页面滚动；只有胶片带内部允许横向滚动。

### 11.5 视觉对照

使用相同视口将：

- `docs/design/desktop-preview-workspace-option-2.png`
- 实现后的批处理截图

放在同一对照画布中检查：

- 照片占比
- 导航与命令栏高度
- 胶片带节奏
- 信息栏宽度
- 字体层级
- 边框、圆角和间距
- 图片裁切
- 主操作层级

至少进行两轮“截图—对照—修正”。不得把生成图中未批准的 CR3、输出质量或模型设置带入实现。

### 11.6 性能回归

重复 M0 的固定样片测试：

- 相同机器
- 相同模型
- 相同处理预设
- 相同样片顺序
- 预热一次
- 至少 3 轮

计算处理中位耗时变化。超过 5% 时：

1. 关闭预取并复测。
2. 降低缩略图并发。
3. 将预览解码安排在任务间隙。
4. 若仍超标，停止发布并定位。

## 12. M8：文档、版本和 RC5

### 12.1 更新用户文档

**修改：**

- `docs/user-guide.md`
- `docs/privacy.md`
- `docs/troubleshooting.md`
- `README.md`
- `RELEASE.md`

内容：

- 胶片带和预览跟随。
- 原图/结果切换。
- 快捷键。
- 预览不可用和文件移动。
- 预览仍然完全本地。
- 本轮不支持 RAW。

### 12.2 更新版本

**修改：**

- `app/version.py`
- `pyproject.toml`
- 安装包元数据中任何受测试约束的版本源

版本统一为：

```text
0.2.0rc5
```

显示版本统一为：

```text
v0.2.0-rc.5
```

运行：

```powershell
python -m pytest tests/unit/test_release_version.py -q
```

### 12.3 完整质量门

```powershell
python -m ruff check app scripts tests
python -m mypy app scripts
python -m pytest tests/unit -q
node --test tests/frontend/*.test.cjs
python -m pytest tests/integration -q
python -m app.main --smoke
```

需要模型的测试必须使用已校验的固定模型；缺模型导致的 skip 不能被当作通过证据。

### 12.4 构建安装包

```powershell
.\packaging\build_release.ps1
```

验证：

- 文件名和版本正确。
- SHA-256 生成。
- 安装后完全离线启动。
- WebView2 资源、CSS、脚本和图标齐全。
- 添加真实样片并完成一批处理。
- 关闭再启动后历史仍可恢复。
- 卸载不删除用户自行保存的输出。

### 12.5 最终证据文档

**新增：**

- `docs/release-evidence-v0.2.0-rc.5.md`

必须记录：

- 提交号
- 测试命令和结果
- 模型校验
- 基线与新版本性能
- 100/500 项胶片带验证
- 窗口与缩放检查
- 无障碍检查
- 视觉对照截图
- 安装包路径、大小和 SHA-256
- 已知限制

## 13. 实施顺序与停止条件

严格按 M0 → M8 顺序。

必须停止并修复的情况：

- 预览接口可以读取任务数据库以外的路径。
- 原片或输出被预览功能写入。
- 预览错误终止批处理。
- 固定预览仍被后台事件切换。
- 100 张胶片带导致无界 DOM 或缓存增长。
- 1040×680 无法访问核心操作。
- 键盘焦点进入不可见区域或被对话框丢失。
- 处理中位耗时回退超过 5%。
- 任一现有恢复、复核或输出测试回归。
- 视觉 QA 只凭单张实现截图、未与目标稿对照。

## 14. 实施阶段 Skill 路由

计划软件批准后：

1. 使用 `product-design:image-to-code`，以已选视觉稿和本规格为唯一视觉目标，实施批处理主工作区。
2. 使用 `ckm:design-system` 落实三层 CSS 变量和组件状态。
3. 使用 `ckm:ui-styling` 进行组件、对话框和无障碍精修，但不引入其 React/Tailwind 栈。
4. 完成后使用 `product-design:audit` 做交互与视觉复审；另把目标稿和实现截图制作成同视口并排对照画布，用同一张对照图逐项判断差异，至少迭代两轮。
5. 使用 `$brainstorming` 的设计结论作为范围边界，不擅自加入视觉稿中的未批准功能。
