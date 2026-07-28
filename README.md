# Remove Number Plate

面向汽车摄影师的离线批量车牌消除工具。拖入图片或文件夹后，软件会自动检测车辆与车牌、扩大完整物理车牌区域，并使用 LaMa 修复车身纹理。

- 不需要训练模型；
- 图片不会离开电脑；
- 支持 JPEG、PNG 与 TIFF；
- 保留安全的 EXIF、ICC 与 DPI 元数据；
- 输出到源目录旁的 `车牌已消除` 文件夹，绝不覆盖原图；
- 低置信度或复杂边缘会进入独立的人工复核区。

## 轻量桌面界面

桌面端使用系统 WebView2 与本地 HTML/CSS/JavaScript，不包含 Qt、Electron 或独立 Chromium。检测和修复统一使用 ONNX Runtime，因此不要求用户安装 CUDA、cuDNN 或 Python。

开发环境启动：

```powershell
python run.py
```

界面包含批处理、待复核、历史记录和设置四个分栏。复核编辑器支持矩形、添加/擦除画笔、删除误检框、撤销/重做、缩放和平移。

## 开发环境

已验证环境为 Windows 10/11 与 Python 3.11：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

模型不提交到普通 Git 历史；版本、来源与 SHA-256 固定在 `models/manifest.json`。
发布模型可以在隔离的 Paddle 3.0/Paddle2ONNX 2.1 环境中从官方源归档重建：

```powershell
python -m scripts.build_models
python -m scripts.verify_models
```

## 开发者批处理命令

```powershell
python -m app.cli process "D:\客户A\成片"
python -m app.cli resume
python -m app.cli report
```

## Windows 打包

```powershell
.\packaging\build_release.ps1
```

脚本会校验模型、运行测试、构建免安装目录与正式安装程序，并执行桌面启动验收。
最终文件位于 `dist\installer`，同目录包含 SHA-256 校验值。

带 `v*` tag 的 GitHub 发布必须配置代码签名证书；缺少签名 secrets 时流水线会拒绝
发布。手动运行 workflow 可以生成明确标记的未签名内部预览。

## 用户文档

- [用户指南](docs/user-guide.md)
- [故障排除](docs/troubleshooting.md)
- [隐私说明](docs/privacy.md)
- [发布检查清单](docs/release-checklist.md)
- [候选版发布说明](RELEASE.md)

## 故障诊断

如果应用无法启动或处理失败，可在“设置 → 诊断与支持”导出 ZIP 诊断包。诊断包只含
版本、运行环境、任务数量和轮转日志，不包含照片、文件路径或任务数据库。
