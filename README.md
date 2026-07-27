# Remove Number Plate

Offline batch license-plate removal for automotive photographers.

The current M2 core supports JPEG, PNG, and TIFF. It detects vehicles and
plates on an NVIDIA GPU, expands the detected text region to cover the complete
physical plate, and reconstructs the bumper with OpenCV's quantized LaMa model.
Users do not train models and images never leave the computer.

## Development environment

The validated Windows environment uses Python 3.11:

```powershell
conda activate plate-remover
pip install -r requirements-dev.txt
pip install -r requirements-inference-cu13.txt
```

Model archives are excluded from Git. Their official URLs and SHA-256 values
are pinned in `models/manifest.json`.

## Batch command

Process one or more images or folders:

```powershell
python -m app.cli process "D:\客户A\成片"
```

Outputs are written in a `车牌已消除` folder beside each source image:

```text
D:\客户A\成片\车牌已消除\IMG_4821_clean.jpg
```

Existing results are never overwritten. Interrupted jobs can be recovered:

```powershell
python -m app.cli resume
python -m app.cli report
```

The lightweight desktop batch interface is now available for development use.

## Desktop preview

The lightweight Windows shell uses the system WebView2 runtime and does not
bundle Qt or a separate Chromium runtime:

```powershell
python run.py
```

All frontend assets are local. The interface makes no network request and the
AI pipeline runs in a dedicated worker thread.

Risky detections appear in the separate `待复核` workspace. The editor supports
rectangles, add/erase brushes, deleting false-positive boxes, undo/redo,
zoom/pan, and one-click local reprocessing.
