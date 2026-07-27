# 全自动车牌消除软件实施计划

日期：2026-07-27  
依据：`docs/superpowers/specs/2026-07-27-license-plate-removal-design.md`  
状态：待实施

## 1. 实施原则

- 先验证模型，再建设界面；
- 每个阶段都必须有可重复的自动化验证；
- 原片安全优先于处理成功率；
- 模型训练不进入用户流程；
- 所有照片和模型推理保持离线；
- 不把未经核验的社区权重加入仓库或安装包；
- 每个里程碑单独提交，便于回滚；
- 模型权重、私有测试照片和运行输出不进入 Git。

## 2. 里程碑与停止条件

| 里程碑 | 交付物 | 继续条件 |
|---|---|---|
| M0 工程基线 | 可测试的包结构、配置和 CI | 单元测试与静态检查通过 |
| M1 模型可行性 | PP-Vehicle 检测与 LaMa 修复基准 | 许可、下载、哈希、推理和样片结果通过 |
| M2 无界面核心 | 可恢复的批处理命令行原型 | 原片安全、状态恢复、错误隔离通过 |
| M3 桌面批处理 | 批处理标签页和进度 | 100 张任务稳定运行 |
| M4 异常复核 | 框、画笔、橡皮擦、撤销重做 | 漏检和误检均可补救 |
| M5 发布候选 | Windows 安装包和许可证清单 | 完整验收通过 |

M1 是硬门槛。若官方预训练模型在代表性商拍样本上明显不适用，不继续开发完整 GUI，应先更换具有清晰许可的预训练模型，或重新确认产品预期。

## 3. M0：工程基线

### 3.1 整理包结构

创建：

```text
app/
  main.py
  config.py
  domain/
    detection.py
    job.py
    result.py
  core/
    detector.py
    inpainter.py
    mask_builder.py
    image_io.py
    risk_gate.py
    job_store.py
    pipeline.py
  gui/
    main_window.py
    batch_page.py
    review_page.py
    history_page.py
    settings_page.py
    review_canvas.py
  infrastructure/
    model_registry.py
    device_probe.py
    logging.py
tests/
  unit/
  integration/
  gui/
scripts/
  verify_models.py
  benchmark_models.py
models/
  manifest.json
```

每个模块只承担规格中定义的一项职责。GUI 仅订阅任务事件，不直接调用模型。

### 3.2 依赖分组

将依赖拆分为：

- `requirements.txt`：运行时；
- `requirements-dev.txt`：pytest、静态检查和打包工具；
- 模型转换工具不进入运行时依赖；
- Paddle Inference 与 ONNX Runtime GPU 先作为两个可选实验环境，M1 后只保留胜出的正式运行时。

当前 `requirements.txt` 中的 `ultralytics`、`simple-lama-inpainting`、`torch` 和 `torchvision` 不直接作为正式发布依赖。删除前先由 M1 记录可替代路径，避免破坏实验复现。

### 3.3 基础质量工具

配置：

- `pytest`；
- `ruff`；
- `mypy` 仅检查核心领域与接口层；
- Windows GitHub Actions：导入测试、单元测试和静态检查；
- 日志不得记录图片像素、EXIF GPS 值或潜在车牌文字。

验证命令：

```powershell
python -m pytest tests/unit -q
python -m ruff check app tests
python -m mypy app/domain app/core
```

提交建议：

```text
chore: establish tested application skeleton
```

## 4. M1：模型与许可证可行性

### 4.1 建立模型清单

`models/manifest.json` 对每个模型记录：

- 稳定模型 ID；
- 版本；
- 官方主页；
- 下载地址；
- 文件名；
- SHA-256；
- 模型格式；
- 输入输出张量；
- 软件许可证；
- 权重使用或再分发条款；
- 转换脚本版本；
- 最低运行时版本。

`ModelRegistry` 只接受清单中的模型，并在加载前校验 SHA-256。正式应用不从随机社区 URL 下载权重。

### 4.2 验证 PP-Vehicle

实现最小检测适配器：

```python
class Detector(Protocol):
    def detect(self, image_rgb: NDArray[np.uint8]) -> list[Detection]:
        ...
```

依次验证：

1. 官方 Paddle 推理模型能在 Windows/NVIDIA 环境运行；
2. 记录模型的真实输入尺寸、归一化方式和输出解码；
3. 尝试官方支持的导出路径；
4. 若 ONNX 输出与官方运行时在固定样本上的框坐标和置信度一致，再选 ONNX Runtime GPU；
5. 若转换不稳定，保留官方 Paddle 部署运行时；
6. 不以安装包体积为由接受明显的精度回退。

建立 20 张技术冒烟样本，覆盖零车牌、单车牌、多车牌、小车牌和贴边车牌。样本可使用有明确许可的公开图片或本地私有照片；私有照片放在被忽略的 `testdata/private/`。

验证输出：

- 每张图的检测框 JSON；
- 冷启动时间；
- 单图中位数和 P95 延迟；
- 峰值显存；
- 模型和运行时磁盘体积；
- 官方运行时与候选部署运行时的差异报告。

### 4.3 验证 LaMa

建立最小修复适配器：

```python
class Inpainter(Protocol):
    def inpaint(
        self,
        image_rgb: NDArray[np.uint8],
        mask: NDArray[np.uint8],
    ) -> NDArray[np.uint8]:
        ...
```

验证：

- 输入输出色彩通道无交换；
- 二值掩码语义正确；
- ONNX 结果与参考实现视觉一致；
- 512、1024 和 1536 像素工作块的延迟与显存；
- 空掩码、全掩码、贴边掩码和多个掩码；
- 输出尺寸和 dtype 不变；
- GPU OOM 可识别并转换为领域错误。

### 4.4 M1 决策记录

新增：

```text
docs/decisions/0001-detector-runtime.md
docs/decisions/0002-inpainter-runtime.md
THIRD_PARTY_NOTICES.md
```

两份决策记录必须包含实测数据和未解决限制。不得只写“ONNX 更轻”之类的主观结论。

验证命令：

```powershell
python -m scripts.verify_models
python -m scripts.benchmark_models --input testdata/private
python -m pytest tests/integration/test_detector_model.py -q
python -m pytest tests/integration/test_inpainter_model.py -q
```

提交建议：

```text
feat: validate offline detection and inpainting runtimes
```

## 5. M2：无界面批处理核心

### 5.1 领域模型

实现不可变数据对象：

- `Detection`：原图坐标、置信度、来源；
- `ImageJob`：输入、输出、状态和错误；
- `MaskRevision`：自动框与人工编辑操作；
- `ProcessingResult`：输出、耗时和风险；
- `RiskReason`：稳定枚举，不把界面文案写入核心。

坐标统一使用方向归一化后的原始像素坐标。预览坐标只能在 GUI 边界转换。

### 5.2 图像读取与安全写出

先写测试，再实现：

- EXIF Orientation 归一化；
- ICC、DPI 和摄影 EXIF 往返；
- JPEG 重用量化表或高质量回退；
- PNG 无损输出；
- TIFF 无损压缩；
- `_clean` 和重名编号；
- 临时文件重新打开校验；
- 同目录原子化改名；
- 失败后不遗留伪装成成功结果的文件。

关键测试：

```text
test_never_overwrites_source
test_normalizes_orientation_once
test_preserves_icc_profile
test_allocates_unique_clean_name
test_rejects_unreadable_temporary_output
```

### 5.3 掩码构建

实现并测试：

- 按短边比例扩张；
- 图像边缘裁剪；
- 多框合并；
- 矩形编辑；
- 画笔增加；
- 橡皮擦删除；
- 处理掩码保持二值；
- 合成 alpha 单独生成。

### 5.4 风险门控

实现版本化预设：

```text
speed
balanced
quality
```

每个决策返回机器可读原因。第一版高风险条件严格按规格实现，不加入无法验证的“AI 审美评分”。

### 5.5 持久任务

使用 Python 标准库 `sqlite3`，数据库放入 `platformdirs` 指定的用户数据目录，不放在照片目录。

表至少包含：

- jobs；
- detections；
- mask revisions；
- processing attempts；
- events；
- application schema version。

事务边界：

1. 开始阶段前记录状态；
2. 文件安全写出完成后才标记 `completed`；
3. 应用启动时把中断的 `detecting`、`inpainting`、`writing` 状态恢复为可重试；
4. 已存在且校验通过的成功输出不重复修复。

### 5.6 管线与 CLI 冒烟入口

增加开发用命令：

```powershell
python -m app.cli process "D:\样片"
python -m app.cli resume
python -m app.cli report
```

CLI 不是最终用户界面，只用于在 GUI 前验证核心。

端到端测试覆盖：

- 10 张混合格式；
- 单图推理失败；
- GPU OOM；
- 输出目录只读；
- 中途终止再恢复；
- 同一文件重复导入；
- 多个输入目录分别输出。

提交建议：

```text
feat: add resumable and metadata-safe batch pipeline
```

## 6. M3：桌面批处理界面

### 6.1 主窗口

实现顶部分栏：

```text
批处理 | 待复核（数量徽标） | 任务历史 | 设置
```

一次只显示一个页面。切换页面不暂停后台任务。

### 6.2 批处理页

实现：

- 文件和文件夹拖放；
- 支持格式过滤与去重；
- 总数、完成、待复核、处理中和失败统计；
- 当前文件名和总进度；
- 暂停、继续、取消剩余任务；
- 进入待复核；
- 打开输出目录；
- 明确显示“完全离线”状态。

任务引擎通过 Qt signals 或线程安全事件桥通知 GUI。主线程不执行图片解码或模型推理。

### 6.3 设置与设备自检

启动时显示：

- GPU 名称；
- 可用执行提供器；
- 模型校验状态；
- 预计运行模式；
- 不兼容驱动或缺失模型的可操作错误。

GUI 测试使用 `pytest-qt`，至少覆盖拖放、分栏切换、按钮状态和任务事件。

提交建议：

```text
feat: add responsive batch processing desktop UI
```

## 7. M4：异常复核编辑器

### 7.1 画布模型

画布内部保存原图坐标操作，不直接修改位图历史。每次编辑记录命令：

- add rectangle；
- remove detection；
- brush add；
- brush erase；
- restore automatic mask。

撤销和重做操作命令栈，因此不会因保存大量全分辨率掩码而快速占用内存。

### 7.2 交互

实现：

- 缩略图队列；
- 大图缩放和平移；
- 检测框选择和删除；
- 矩形新增；
- 画笔与橡皮擦；
- 画笔尺寸；
- 掩码透明度；
- 撤销、重做；
- 恢复自动框；
- 跳过；
- 确认并重修；
- 处理下一张的键盘快捷键。

保存人工操作到 SQLite。重修失败时保留编辑，不要求用户重画。

### 7.3 视觉和坐标测试

重点测试：

- 高 DPI 缩放；
- 窗口缩放后的坐标映射；
- EXIF 旋转图片；
- 画布缩放后画笔半径；
- 贴边矩形；
- 撤销重做一致性；
- 重启后恢复人工掩码。

提交建议：

```text
feat: add exception review and mask editing workflow
```

## 8. M5：发布候选

### 8.1 私有实拍验收

准备至少 100 张代表性商拍照片。建立不包含 OCR 文本的匿名结果表：

- visible plate count；
- detected plate count；
- false positive count；
- auto delivered；
- requires review；
- rejected；
- failure category；
- latency；
- peak VRAM。

计算：

- 车牌召回率；
- 图片级误修率；
- 自动结果可交付率；
- 中位数和 P95 耗时；
- 失败类别分布。

达到规格指标后才进入打包。未达到时先对失败类别做决策，不通过降低统计口径宣布成功。

### 8.2 Windows 打包

优先构建目录式安装包，而不是单文件自解压 EXE：

- 启动更快；
- Qt、GPU 运行时和许可证文件可见；
- LGPL 动态库替换更清晰；
- 模型可独立更新和校验。

打包内容：

- 应用；
- Qt 动态库；
- 选定推理运行时；
- 固定模型；
- `THIRD_PARTY_NOTICES.md`；
- 许可证文本；
- 用户指南；
- 模型来源和哈希清单。

验证干净 Windows 机器：

- 无 Python 环境可启动；
- 无网络可完成任务；
- 不访问云端；
- NVIDIA 兼容驱动下启用 GPU；
- 路径含中文、空格和长文件名；
- 普通用户权限可运行；
- 卸载不删除用户照片和输出。

### 8.3 发布文档

更新：

```text
README.md
docs/user-guide.md
docs/troubleshooting.md
docs/privacy.md
THIRD_PARTY_NOTICES.md
```

README 不承诺未经实测的速度和精度。发布说明写明测试 GPU、驱动、图片分辨率、样本规模和限制。

提交建议：

```text
release: prepare first offline Windows candidate
```

## 9. Git 与发布节奏

每个里程碑使用短生命周期分支：

```text
feat/m0-foundation
feat/m1-model-spike
feat/m2-core-pipeline
feat/m3-batch-ui
feat/m4-review-editor
release/v0.1.0
```

合并前必须满足该里程碑验证命令。模型二进制不进入普通 Git；若允许再分发，放入版本化发布资产或安装器资源，并始终核对 SHA-256。

## 10. 首个实施批次

开始实现时只执行 M0 与 M1，不并行建设 GUI。首批具体顺序：

1. 修复当前不完整的 `app/config.py`，让包可导入；
2. 建立领域接口和测试工具；
3. 建立模型清单与校验器；
4. 下载并核验 PP-Vehicle 官方推理权重；
5. 用 20 张冒烟样本比较官方运行时和 ONNX 候选；
6. 下载并核验 LaMa 官方权重；
7. 完成局部修复基准；
8. 写两份运行时决策记录；
9. 向用户报告模型能否满足进入完整开发的门槛。

该批次不会修改原始照片，不会上传图片，不会训练模型，也不会开始复杂 GUI。
