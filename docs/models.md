# 模型说明

本项目的核心功能是「车辆检测 → 车牌检测 → 图像修复」三阶段流水线。检测与修复统一使用 ONNX Runtime 运行，因此生产环境不要求安装 Paddle、CUDA 或 cuDNN。模型二进制文件不提交到 Git，版本、来源与 SHA-256 固定在 `models/manifest.json` 中，任何人可按本文档所述命令从官方源重建或校验。

## 1. 流水线总览

处理一张图片时，按以下顺序执行：

1. **车辆检测**（`PP-YOLOE-S`）：在整张图中找出所有车辆区域；
2. **车牌检测**（`PP-OCRv3 DB`）：对每个车辆区域裁剪块，在其内部检测车牌，得到车牌透视轮廓；此外再对整图执行一次车牌检测兜底，两者按 IoU 去重合并，以召回「车辆漏检 / 无车辆」场景下未被发现的车牌；
3. **图像修复**（`LaMa`）：沿车牌轮廓生成遮罩，用周围的背景纹理修复/填补车牌区域。

采用「先车后牌」的两阶段检测，是因为车牌通常较小，直接在整图上检测容易漏检；先定位车辆，再在放大的车辆裁剪块内检测车牌，可显著提升精度。车牌检测结果上游由 `app/core/two_stage_detector.py` 聚合回原图坐标。

## 2. 模型清单

| 模型 ID | 用途 | 格式 | 来源 | 许可证 | 启用 |
|---------|------|------|------|--------|------|
| `pp_yoloe_s_vehicle` | 车辆检测（Paddle 原始归档，转换源） | paddle-inference-archive | PaddleX 3.0.0 | Apache-2.0 | 否 |
| `pp_vehicle_plate_detector` | 车牌检测（Paddle 原始归档，转换源） | paddle-inference-archive | PaddleDetection b25522a | Apache-2.0 | 否 |
| `ppyoloe_vehicle_onnx` | 车辆检测（生产 ONNX） | onnx-opset14 | PaddleX 3.0.0 → Paddle2ONNX 2.1.0 转换 | Apache-2.0 | 是 |
| `ppvehicle_plate_onnx` | 车牌检测（生产 ONNX） | onnx-opset14 | PaddleDetection b25522a → Paddle2ONNX 2.1.0 转换 | Apache-2.0 | 是 |
| `migan_inpainter` | 图像修复（实验，已弃用） | onnx | MI-GAN 官方预转换 | MIT | 否 |
| `opencv_lama_inpainter` | 图像修复（生产 ONNX） | onnx | OpenCV `inpainting_lama` 仓库 | Apache-2.0 | 是 |

> 说明：两个 Paddle 原始归档（`pp_yoloe_s_vehicle`、`pp_vehicle_plate_detector`）本身不参与生产推理，仅作为「离线转换」的源模型，用于重建对应的 ONNX 权重。`migan_inpainter` 曾在视觉评审中失败，现已停用，保留记录仅供追溯。

## 3. 各模型详解

### 3.1 车辆检测：`PP-YOLOE-S`

- **角色**：流水线第一阶段，在整图中定位车辆。
- **文件**：`ppyoloe_vehicle.onnx`（生产）。
- **输入**：`image`（1×3×640×640，RGB，归一化到 ImageNet 均值/方差）；`scale_factor`（1×2，缩放比例）。
- **输出**：N×6 张量，每行形如 `[类别, 置信度, x1, y1, x2, y2]`。
- **预/后处理**：见 `app/infrastructure/paddle_vehicle_detector.py`；
  ONNX 推理适配见 `app/infrastructure/onnx_detectors.py` 的 `OnnxVehicleDetector`。
- **来源与转换**：官方 PaddleX 3.0.0 推理归档，用 Paddle2ONNX 2.1.0（opset14）本地转换，未重新训练。
- **许可**：Apache-2.0。

### 3.2 车牌检测：`PP-OCRv3 DB`

- **角色**：流水线第二阶段，在车辆裁剪块内检测车牌，输出带透视角度的轮廓。
- **文件**：`ppocrv3_plate.onnx`（生产）。
- **输入**：`images`（BGR、短边限长 960、长边按最大比例缩放、尺寸对齐到 32 的倍数），通道按 ImageNet 均值/方差归一化。
- **输出**：1×1×H×W 的 DB 概率图。
- **预/后处理**：DB 概率图通过轮廓查找、最小外接矩形、unclip 扩张等解码为原图透视角点（见 `app/infrastructure/paddle_plate_detector.py` 的 `decode_db_map`）；
  ONNX 推理适配见 `app/infrastructure/onnx_detectors.py` 的 `OnnxPlateDetector`。
- **来源与转换**：官方 PaddleDetection b25522a PP-Vehicle 车牌模型归档，用 Paddle2ONNX 2.1.0（opset14）本地转换，未重新训练。
- **许可**：Apache-2.0。DB 后处理算法部分改编自 PaddleOCR（Apache-2.0，见文件头注释）。

### 3.3 图像修复：`LaMa`

- **角色**：流水线第三阶段，用车牌周围的背景纹理填补车牌区域。
- **文件**：`inpainting_lama_2025jan.onnx`（生产，量化版，单文件）。
- **输入**：`image`（512×512 方形上下文裁剪，BGR、归一化到 [0,1]）；`mask`（512×512，遮罩）。
- **输出**：`output`（512×512×3，修复后的图像块）。
- **预/后处理**：围绕遮罩区域取方形上下文裁剪（默认 4× 上下文），推理后做高斯羽化合成回原图，保证未选中像素逐位不变（见 `app/infrastructure/lama_inpainter.py`）。
- **来源**：OpenCV 账户发布的 `inpainting_lama` 仓库，仓库内文件均声明 Apache-2.0。
- **许可**：Apache-2.0。

### 3.4 已停用模型（仅供追溯）

- **`MI-GAN`（`migan_inpainter`，MIT）**：曾作为修复备选，官方仓库的预转换 ONNX 模型。输入沿用「mask 翻转」约定（已知区域为 255），输出为直接修复结果，并保证未选中像素逐位不变。视觉评审未通过后已停用，代码保留在 `app/infrastructure/migan_inpainter.py`。

## 4. 获取与校验模型

模型二进制不随仓库分发，需按以下命令从官方源下载/重建并在载入前校验 SHA-256：

```powershell
python -m scripts.build_models   # 下载官方源并重建/校验所有启用模型
python -m scripts.verify_models  # 校验已下载模型的 SHA-256 并输出设备信息
```

- `build_models` 会从 `manifest.json` 记录的官方 URL 下载源归档，对 ONNX 模型做 Paddle2ONNX 重转换，并验证产物的 SHA-256 与清单一致（可复现）。
- `verify_models` 输出每个模型的 `enabled / exists / verified` 状态、来源 URL 以及 GPU/ONNX providers 信息，任一带 `enabled` 的模型未通过校验时返回非零退出码。

## 5. 依赖说明

- **运行/推理**：仅需 `onnxruntime`（CPU 执行）。应用在首次启动或处理时调用上述脚本准备模型。相关依赖见 `requirements.txt`。
- **离线重建（仅开发者）**：转换 ONNX 的过程需要隔离的 Paddle 3.0.0 与 Paddle2ONNX 2.1.0 环境（见 `scripts/build_models.py` 的版本校验），但这**不在**生产运行时依赖中。
- 推理相关依赖的 CUDA 13 变体另见 `requirements-inference-cu13.txt`，其中明确说明生产运行时采用转换后的 ONNX 权重，不要求 Paddle 或单独打包的 CUDA/cuDNN。

## 6. 许可与版权

- 各模型自身的开源许可（Apache-2.0 / MIT）以上表及 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 为准，再分发仍需符合其原始许可。
- 本项目为源码公开（source-available）的**非商用许可**项目，完整条款见 [LICENSE](../LICENSE)。本项目引用的第三方开源组件仍受其各自原始许可约束。