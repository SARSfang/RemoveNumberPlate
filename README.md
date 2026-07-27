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

## 开发者批处理命令

```powershell
python -m app.cli process "D:\客户A\成片"
python -m app.cli resume
python -m app.cli report
```

## Windows 打包

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\plate_clear.spec
```

生成的 `dist\消除车牌` 是完整的免安装目录。
