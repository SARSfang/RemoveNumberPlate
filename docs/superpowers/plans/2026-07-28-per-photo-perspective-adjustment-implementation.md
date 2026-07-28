# 每张照片四点透视调整实施计划

**日期：** 2026-07-28  
**状态：** 等待实施  
**对应规格：** [每张照片四点透视调整设计规格](../specs/2026-07-28-per-photo-perspective-adjustment-design.md)  
**目标版本：** `v0.2.0-rc.6`

## 1. 实施原则

1. 严格按“测试先行 → 最小实现 → 定向回归 → 独立提交”的顺序推进。
2. 保持 WebView2、原生 HTML/CSS/JavaScript、Python 和 ONNX Runtime，不增加网络、训练或付费依赖。
3. 四点坐标始终使用 EXIF 方向归一化后的原图像素坐标；前端预览坐标只用于显示换算。
4. 所有桥接方法只接收任务 ID、命令和不透明 token，不接收任意文件路径。
5. 临时预览不得写入正式输出目录；正式保存不得再次运行 LaMa。
6. 旧数据库、旧矩形任务、现有复核入口和原片不覆盖约束必须保持兼容。
7. 私有实拍只用于本机验收，不提交到 Git、测试夹具或诊断包。

## 2. 里程碑与提交边界

| 里程碑 | 结果 | 建议提交 |
|---|---|---|
| M0 | 锁定 RC5 基线和四张私有样片清单 | `test: lock perspective adjustment baseline` |
| M1 | 四点领域对象和检测器输出 | `feat: preserve plate quadrilaterals` |
| M2 | 数据库模式 4 与旧任务兼容 | `feat: persist detection polygons` |
| M3 | 多边形遮罩与命令校验 | `feat: build editable perspective masks` |
| M4 | 临时预览文件与 token 会话 | `feat: add local adjustment preview sessions` |
| M5 | 通用任务调整桥接与事件 | `feat: expose per-photo adjustment workflow` |
| M6 | 主预览入口和四点编辑器 | `feat: add per-photo perspective editor` |
| M7 | 固定免安装测试版 | `build: add stable preview build` |
| M8 | 真实样片 QA、文档和 RC6 | `release: prepare v0.2.0 rc6` |

## 3. M0：基线与失败测试

### 3.1 基线检查

执行：

```powershell
git status --short
.\.venv-rc5\Scripts\python.exe -m pytest tests\unit -q
.\.venv-rc5\Scripts\python.exe -m pytest tests\integration -q
node --test tests\frontend\*.test.cjs
.\.venv-rc5\Scripts\python.exe -m ruff check app tests scripts
.\.venv-rc5\Scripts\python.exe -m mypy app
```

记录测试数量、跳过原因、安装包版本和当前 Git 提交。工作树若出现不属于本计划的修改，先停下核对，不覆盖。

### 3.2 私有样片清单

在 Git 已忽略的 `testdata/private/perspective-rc6/` 放入用户四张实拍，生成仅含以下字段的本地清单：

- 文件名；
- 字节数；
- SHA-256；
- 用户对 RC5 的 A/B/C/D 评级；
- “区域过大、边缘衔接、漏检”等非敏感标签。

清单也保持 Git 忽略，不记录照片路径到正式日志。

### 3.3 先建立失败测试

新增或扩展测试，使以下能力在实现前明确失败：

- 检测结果没有四点；
- 数据库无法持久化四点；
- 透视框仍被转成大水平矩形；
- `COMPLETED` 和 `NO_PLATE` 任务不能打开调整；
- 临时预览会直接增加正式输出文件；
- 继续编辑后旧 token 仍可保存；
- 主预览没有“调整区域”入口。

## 4. M1：四点领域对象与检测器

### 4.1 四边形值对象

修改：

- `app/domain/detection.py`
- `tests/unit/test_detection.py`（新增）

增加不可变 `Quadrilateral`：

```text
points: (left_top, right_top, right_bottom, left_bottom)
```

验证：

- 恰好四个二维有限数值点；
- 坐标非负；
- 不自交；
- 顶点按顺时针固定顺序；
- 面积大于最小浮点容差；
- 可计算 `area`、`bounding_box` 和裁剪后的点。

`Detection` 在现有 `source_tile` 后增加 `polygon: Quadrilateral | None = None`，避免破坏旧位置参数。提供 `effective_polygon`，旧记录为空时返回外接矩形四角。

先写测试：

- 合法梯形；
- 零面积；
- 蝴蝶形自交；
- 错误点序；
- 外接框；
- 旧矩形回退；
- 裁剪到图像边缘。

### 4.2 DB 解码保留四点

修改：

- `app/infrastructure/paddle_plate_detector.py`
- `tests/unit/test_paddle_plate_detector.py`

`decode_db_map` 将已计算的 `expanded_box` 映射回原图，构造 `Quadrilateral`，再由其计算 `BoundingBox`。不再只保留 `min/max x/y`。

ONNX OCR 检测器复用该解码函数，增加回归证明 ONNX 路径也返回四点。

验证：

```powershell
.\.venv-rc5\Scripts\python.exe -m pytest tests\unit\test_detection.py tests\unit\test_paddle_plate_detector.py tests\unit\test_onnx_detectors.py -q
.\.venv-rc5\Scripts\python.exe -m mypy app\domain app\infrastructure
```

## 5. M2：数据库模式 4

修改：

- `app/core/job_store.py`
- `tests/unit/test_job_store.py`

将 `SCHEMA_VERSION` 从 3 升到 4；`detections` 新增可空 `polygon_json TEXT`。

写入规则：

- 新检测必须序列化四点；
- 兼容测试可写空值；
- JSON 只包含四组数值坐标，不含路径或额外对象。

读取规则：

- 有合法 JSON 时恢复 `Quadrilateral`；
- 空值时使用原矩形四角；
- 非法 JSON 视为数据库内容错误，不静默猜测。

迁移测试必须从真实模式 3 表结构开始，证明：

- 原任务、结果、风险、耗时、mask revisions 均保留；
- 新列存在且旧行为空；
- 旧行读取为矩形四点；
- 新行四点 round-trip 精确；
- `quick_check` 仍通过；
- 高于版本 4 的数据库仍拒绝打开。

验证：

```powershell
.\.venv-rc5\Scripts\python.exe -m pytest tests\unit\test_job_store.py -q
.\.venv-rc5\Scripts\python.exe -m ruff check app\core\job_store.py tests\unit\test_job_store.py
```

## 6. M3：透视遮罩与编辑命令

### 6.1 多边形遮罩

修改：

- `app/core/mask_builder.py`
- `tests/unit/test_mask_builder.py`

将默认策略改为：

```text
margin_ratio = 0.08
minimum_margin_ratio = -0.15
maximum_margin_ratio = 0.35
```

实现：

1. 读取 `effective_polygon`；
2. 使用现有 `pyclipper` 按多边形短边比例做正负偏移；
3. 将结果裁剪到图像范围；
4. 使用 `cv2.fillPoly` 填充；
5. 多检测取并集。

删除默认流程中原有左右约一个框高、上下 40% 的轴对齐扩张；不得保留双重扩张。

测试：

- 梯形遮罩不会填充外接矩形四角；
- 默认 8% 外扩；
- -15% 缩小；
- +35% 上限；
- 边界裁剪；
- 多框并集；
- 旧矩形兼容；
- 偏移导致多边形消失时返回明确校验错误。

### 6.2 命令解析与校验

新增：

- `app/core/adjustment_commands.py`
- `tests/unit/test_adjustment_commands.py`

把命令解析从画 mask 的过程分离，形成单一受信任入口：

- `set_detection_polygon`
- `add_polygon`
- `remove_detection`
- `brush_add`
- `brush_erase`
- `set_margin`

每条命令带稳定目标 ID；自动框使用 `detection:<ordinal>`，新增框使用前端生成的 UUID。后端重新验证 UUID 格式和目标存在性。

限制：

- 总命令不超过 10,000；
- 单笔画点数不超过 20,000；
- 笔刷半径 1–500 原图像素；
- margin -0.15–0.35；
- 点必须有限、裁剪前不得使用极端数值；
- 四边形不得自交且须满足最小面积。

### 6.3 手动遮罩兼容

修改：

- `app/core/manual_mask.py`
- `tests/unit/test_manual_mask.py`

`build_manual_mask` 先用命令解析器得到最终四边形集合和 margin，再生成多边形 mask，最后依序应用画笔。旧 `rectangle` 修订继续读取，但新前端不再写该命令。

验证：

```powershell
.\.venv-rc5\Scripts\python.exe -m pytest tests\unit\test_mask_builder.py tests\unit\test_adjustment_commands.py tests\unit\test_manual_mask.py -q
.\.venv-rc5\Scripts\python.exe -m mypy app\core
```

## 7. M4：临时预览会话

### 7.1 可复用渲染输出

修改：

- `app/core/pipeline.py`
- `app/core/image_io.py`
- 对应单元与集成测试

将 `ManualMaskProcessor` 拆成：

- `render_to(source, mask, cache_target)`：运行一次 LaMa，保留元数据并写入已验证缓存文件；
- `process(source, mask)`：为旧调用保留，内部复用 `render_to` 后提交到版本化输出。

增加 `copy_verified_image_atomic(cache_source, output)`：

- 目标必须不存在；
- 先复制到目标目录隐藏临时文件；
- 验证格式、可解码性和尺寸；
- 使用原子 rename 完成；
- 失败清理临时文件。

这样正式保存只复制已验证缓存，不重新推理、不重新编码。

### 7.2 会话管理器

新增：

- `app/core/adjustment_session.py`
- `tests/unit/test_adjustment_session.py`

会话记录：

```text
job_id
revision
commands_digest
preview_token
cache_path
created_at
width / height
```

规则：

- token 使用 `secrets.token_urlsafe`，不可预测；
- token 与 job、revision、命令摘要绑定；
- 30 分钟过期；
- 重新预览、继续编辑、取消、保存或退出使旧 token 失效；
- 只保留一个活动会话和一个缓存文件；
- 应用启动时清理 `data_dir/adjustment-cache` 遗留文件；
- 清理失败只记本地日志，不阻止应用启动。

测试 token 重放、任务错配、修订错配、过期、清理和缓存目录逃逸。

## 8. M5：桥接 API 与事件

修改：

- `app/desktop.py`
- `tests/unit/test_desktop.py`
- 必要时新增 `app/core/adjustment_service.py`

### 8.1 `get_adjustment_job`

允许状态：

- `COMPLETED`
- `NO_PLATE`
- `REVIEW_REQUIRED`
- `FAILED`
- `CANCELLED`

拒绝处理中状态和缺失原图。返回：

- ID、短文件名、状态；
- 原图数据 URL、原图与预览尺寸；
- 四点检测和 confidence；
- 最新修订命令；
- 是否已有结果；
- 风险标签；
- `entry_available` 与安全中文原因。

不得返回 source、output 或 cache 路径。

### 8.2 `preview_adjustment`

参数：`job_id, revision, commands`。

行为：

1. 校验任务和原图；
2. 校验当前没有批处理或另一调整推理；
3. 后端解析命令并生成 mask；
4. 异步 `render_to` 缓存；
5. 创建 token；
6. 发送受限尺寸数据 URL 预览。

事件：

- `adjustment_preview_started`
- `adjustment_preview_ready`
- `adjustment_preview_failed`

返回只表示任务是否接受；实际结果通过事件到达。事件不包含路径。

### 8.3 `save_adjustment`

参数：`job_id, preview_token`。

行为：

- 重新校验 token；
- `allocate_output_path` 选择 `_clean_2` 等名称；
- 原子复制缓存；
- 在一个数据库事务中记录 mask revision、更新最新 output、状态 `COMPLETED`、清空旧 risks，同时保留 detections；
- 清理会话；
- 发送 `adjustment_saved` 和 `history_changed`。

为避免当前 `record_result` 删除 detections，增加明确的“保留检测”更新路径；不得依靠手动处理结果伪造空 detections。

### 8.4 取消与退出

`cancel_adjustment(job_id)` 使当前 token 失效并清理缓存。若 LaMa 已开始则不强杀线程；完成后丢弃结果并不得发出 ready 事件。

回归现有 `reprocess_review`：短期改为调用新流程的“预览＋立即保存”兼容适配，前端迁移完成后再移除旧直写路径。迁移期间只保留一个模型锁。

验证：

```powershell
.\.venv-rc5\Scripts\python.exe -m pytest tests\unit\test_desktop.py tests\unit\test_adjustment_session.py -q
.\.venv-rc5\Scripts\python.exe -m pytest tests\integration\test_headless_pipeline.py -q
```

## 9. M6：前端入口与四点编辑器

### 9.1 主预览入口

修改：

- `app/web/index.html`
- `app/web/batch/workspace.js`
- `app/web/styles/batch.css`

在主预览顶部右侧、详情按钮之前增加“调整区域”。状态规则由当前 job 驱动：

- 非处理中且原图可用：启用；
- 处理中：禁用并提示处理完成后可调整；
- 原图缺失：禁用并提示原因；
- 无当前任务：隐藏。

点击后：

- 记录返回上下文为 `batch + selected job id + preview variant`；
- 导航到现有复核页；
- 调用通用调整加载方法，不改变任务状态、不加入待复核队列。

### 9.2 编辑器状态重构

修改：

- `app/web/review/editor.js`
- `app/web/index.html`
- `app/web/styles/review.css`
- `app/web/core/shortcuts.js`

编辑器增加模式：

- `queue`：从“待复核”导航进入，左栏显示风险队列；
- `single`：从主预览进入，左栏显示“当前照片”，保存或取消后返回原批处理照片。

页面标题在 single 模式显示“调整消除区域”。两种模式共享同一画布、工具和 API。

状态新增：

```text
polygons
selectedPolygonId
marginRatio
commands / redoCommands
revision
previewToken
previewImage
viewVariant: mask | result
phase: editing | rendering | preview_ready | saving | failed
returnContext
```

### 9.3 四点交互

实现纯几何函数并导出给 Node 测试：

- 命中四角；
- 命中多边形内部；
- 拖单角；
- 拖整体；
- 预览坐标与原图坐标互转；
- 自交和最小面积预检查；
- margin 滑杆 -15%–35%、步进 1%。

工具：

- 四点框；
- 新增车牌框；
- 画笔补充；
- 橡皮擦；
- 删除框；
- 恢复自动框；
- 撤销/重做。

保持现有误触保护、指针取消、Space 平移和离开确认。新增四点框默认在当前可视区域中心创建一个不自交的小梯形。

### 9.4 预览与保存 UI

编辑阶段主按钮为“生成临时预览”。ready 后：

- 自动切到“临时结果”分栏；
- 显示“继续调整”“保存新结果”“取消并返回”；
- 继续调整立即使 token 在前端失效并通知后端取消；
- 保存期间禁止重复提交；
- 保存成功后刷新任务、预览、胶片带和历史，并返回来源页面；
- queue 模式保存后加载下一条待复核任务。

任何编辑都会令已有预览过期。生成失败保留全部命令并显示重试。

### 9.5 前端测试

新增：

- `tests/frontend/adjustment-state.test.cjs`
- `tests/frontend/quadrilateral-editor.test.cjs`

扩展测试桥：

- completed/no_plate/review_required/failed/cancelled；
- 无检测空编辑器；
- 多车牌；
- preview started/ready/failed；
- token 失效；
- save success/failure；
- 返回上下文。

视觉回归：

- 1487×1058；
- 1040×680；
- 200% 缩放；
- queue 和 single 两种模式；
- 原图遮罩、渲染中、临时结果、错误和未保存确认。

验证：

```powershell
node --check app\web\review\editor.js
node --check app\web\batch\workspace.js
node --test tests\frontend\*.test.cjs
.\.venv-rc5\Scripts\python.exe -m pytest tests\unit\test_desktop.py -q
```

## 10. M7：固定免安装测试版

新增：

- `packaging/build_preview.ps1`
- `启动测试版.cmd`
- `tests/unit/test_preview_build_script.py`

`build_preview.ps1`：

1. 使用与正式构建相同的 Python 3.11/3.12 探测逻辑；
2. 要求桌面程序已关闭，否则明确报错；
3. 校验模型；
4. 默认运行 Python、Node、ruff 和 mypy；支持仅供已验证流水线使用的 `-SkipTests`；
5. 使用 PyInstaller：

```text
--distpath dist\preview
--workpath build\preview
packaging\plate_clear.spec
```

6. 对 `dist\preview\消除车牌\消除车牌.exe --smoke`；
7. 写入 `dist\preview\BUILD.txt`，包含版本、Git commit、时间和 smoke 结果。

`启动测试版.cmd` 只启动稳定路径；文件不存在时显示“请先生成测试版”，不自动安装、不修改注册表。

同步修改正式 `build_release.ps1` 的可执行文件查找逻辑，使其只选择正式 `dist\消除车牌\消除车牌.exe`，明确忽略 `dist\preview`，避免两个构建互相干扰。

验收：

- 首次生成后可创建一个固定桌面快捷方式；
- 后续关闭程序、重新构建、双击同一快捷方式即可；
- 覆盖测试程序不删除设置、历史或输出照片；
- 不出现安装项或卸载项；
- 正式安装包构建仍通过。

## 11. M8：回归、真实样片与 RC6

### 11.1 全量自动验证

```powershell
.\.venv-rc5\Scripts\python.exe -m pytest -q
node --test tests\frontend\*.test.cjs
.\.venv-rc5\Scripts\python.exe -m ruff check app tests scripts
.\.venv-rc5\Scripts\python.exe -m mypy app
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_preview.ps1
```

记录可选 Paddle 跳过项；正式启用的 ONNX 三模型必须通过完整性和 smoke。

### 11.2 四张私有实拍验收

逐张记录：

- 自动四点是否贴合透视；
- 默认 8% 是否覆盖完整车牌但不过度吞掉车身；
- 调整所需角点移动次数；
- 临时预览前后输出目录文件数；
- 保存后新增文件名；
- 原图和旧结果哈希；
- 用户 A/B/C/D 评级。

硬性通过条件：

1. 四张均能从主预览两步内进入调整。
2. 斜拍遮罩不是水平外接大矩形。
3. 临时预览不新增正式文件。
4. 保存只新增一个版本。
5. 原图和旧结果哈希不变。
6. 至少解决本轮用户指出的“区域过大”主问题；边缘衔接若仍不理想，保留样片证据进入下一轮参数优化，不在本里程碑擅自更换模型。

### 11.3 文档与版本

更新：

- `docs/user-guide.md`
- `docs/troubleshooting.md`
- `docs/release-checklist.md`
- `README.md`
- `RELEASE.md`
- `app/version.py`
- `pyproject.toml`
- `packaging/installer.iss`
- `packaging/version_info.txt`

统一版本为 `0.2.0-rc.6` / Windows 数字版本 `0.2.0.6`。说明：

- 每张照片可调整；
- 四点透视框；
- 临时预览；
- 固定免安装测试版；
- 不训练、不联网、不收费；
- 旧数据库自动兼容；
- 未签名候选版的 Windows 信誉提示。

### 11.4 正式候选包

在固定测试版通过用户验收后才运行正式构建：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_release.ps1
```

要求：

- 安装、启动、处理、卸载通过；
- SHA-256 写入 `dist\installer\SHA256SUMS.txt`；
- Git 工作树干净；
- 审计文档包含自动测试、视觉截图、四张私有样片的非敏感结果摘要和已知限制。

## 12. 完成定义

只有以下全部成立才完成：

- 新检测端到端保留四点，旧检测正常回退。
- 每张非处理中照片都有按需调整入口。
- 四点、多车牌、画笔、橡皮擦、撤销/重做可用。
- 临时预览和正式保存严格分离，token 保护通过。
- 保存后保留 detections、mask revisions、旧输出和原图。
- 数据库模式 3→4 迁移与损坏恢复通过。
- 1040×680、宽屏和 200% 缩放完成视觉验收。
- 固定免安装测试入口可重复使用。
- 四张私有实拍完成用户复验。
- 全量测试、preview smoke 和最终安装器验收通过。
