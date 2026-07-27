# Implementation progress

Updated: 2026-07-28

## Environment

- Operating system: Windows 10/11 (`Windows_NT`)
- GPU: NVIDIA GeForce RTX 4060 Ti, 8188 MiB
- NVIDIA driver: 610.74
- Miniconda: 26.5.3
- Project environment: `plate-remover`
- Python: 3.11.15
- Environment source: conda-forge

The system Python 3.14.2 is intentionally not used because GPU inference
packages may not provide compatible wheels.

## Milestones

- M0 engineering baseline: complete
- M1 reference model and license feasibility: complete; private-photo visual
  acceptance remains pending
- M2 headless pipeline: complete
- M3 lightweight batch desktop UI: in progress
- M4 exception review editor: pending
- M5 Windows release candidate: pending

## Current decisions

- No user training or annotation workflow.
- Ultralytics, PyTorch, and `simple-lama-inpainting` are not production
  dependencies.
- The production runtime is PP-YOLOE-S vehicle detection followed by the
  PP-Vehicle plate detector on the GPU, with OpenCV LaMa ONNX on the CPU.
- Enabled model artifacts and SHA-256 values are verified before processing.
  Redistribution approval remains a separate release gate documented in
  `THIRD_PARTY_NOTICES.md`.

## M0 verification

- 41 unit tests passed; one ASCII-path staging case is skipped only because the
  repository itself is under a Chinese path.
- Ruff passes for application code, scripts, and tests.
- Strict mypy passes for all 25 checked application and script modules.
- Four integration tests pass with the pinned official models.
- `run.py` imports successfully and detects the NVIDIA GPU.

## M1 findings

- The official PP-Vehicle flow first detects vehicles, crops each vehicle, and
  then runs the plate detector.
- The plate detector is a PP-OCRv3 text detector fine-tuned on CCPD2019 and
  CCPD2020, not a one-stage whole-photo object detector.
- Official archive downloaded locally and pinned:
  `acc7eb42b299cdb4eed2999f4de99c89555767b321c272a9878f688d24503fd9`.
- Direct tiled full-photo detection and vehicle-first detection must both be
  benchmarked before choosing the production architecture.
- The official lightweight `PP-YOLOE-S_vehicle` inference archive is
  30,279,680 bytes and is pinned at SHA-256
  `1143b3e62e1716ed056870f3788da77457b932cc7efa10b3abca5d24f61d0b2e`.
- On PaddleDetection's 1920 x 1280 sample, whole-image plate detection found
  no plate. A vehicle crop with the official `min/736` setting found the plate
  at confidence 0.9023.
- The automatic vehicle-first GPU integration test passes on the RTX 4060 Ti:
  confidence 0.8941 and 0.428 seconds for the 1920 x 1280 official sample after
  a 3.31-second model startup.
- Detector runtime decision: use PP-YOLOE-S vehicle detection followed by the
  PP-Vehicle plate detector. See `docs/decisions/0001-detector-runtime.md`.
- Initially replaced the 381 MB Big-LaMa candidate with the official MI-GAN
  project's 28,079,181-byte ONNX pipeline. SHA-256:
  `6f1f3530a1a2324b19752018ce756088b07973cda8d7d890034ace5c8a48c40b`.
- MI-GAN uses ONNX Runtime CPU: 0.276 seconds for a 512 x 512 synthetic case
  and 0.312 seconds for the 1920 x 1280 official vehicle sample. The tested GPU
  provider was slower at 0.441 seconds and would add a much larger runtime.
- Visual review rejected MI-GAN: it created an obvious red patch, used a hard
  edge, and retained the blue country strip. Inference success is no longer
  treated as visual acceptance.
- The OpenCV quantized LaMa artifact is pinned at SHA-256
  `7df918ac3921d3daf0aae1d219776cf0dc4e4935f035af81841b40adcf74fdf2`.
  It is 92,591,623 bytes and ran the sample crop in about 1.33 seconds after a
  3.62-second session startup.
- Inpainting runtime decision: OpenCV LaMa ONNX on a square context crop, with
  full-plate mask expansion and feathered compositing. See
  `docs/decisions/0002-inpainter-runtime.md`.
- Follow-up visual review found residual edge transitions. The production
  default now removes a larger region around the detected text box
  (left 0.95x, right 1.00x, top/bottom 0.40x box height) and uses a 12-pixel
  bidirectional feather. On the official close-up this removes the plate frame,
  mounting shadow, and adjacent decal while continuing the bumper texture.

## M2 verification

- The headless batch pipeline discovers JPEG, PNG, and TIFF inputs, skips its
  own output directories, and isolates failures per image.
- Outputs are written atomically to a `车牌已消除` subdirectory. Existing files
  are never overwritten; `_clean_2`, `_clean_3`, and later suffixes are used.
- EXIF orientation is normalized once. Safe EXIF, ICC, DPI, JPEG quantization,
  and subsampling metadata are retained where the source format supports them.
- SQLite job state records completed, review-required, no-plate, and failed
  results. Jobs interrupted during processing return to the queue on resume.
- Risk gating prevents uncertain, tiny, edge-touching, abnormal, or overlapping
  detections from being edited automatically.
- Ruff and strict mypy pass. The test suite has 59 passing unit tests (one
  non-ASCII staging test skipped) and five passing real-model integration tests.
- A real CLI smoke test completed in 1.82 seconds and produced
  `output/m2_smoke/车牌已消除/sample_clean_2.jpg`.

## M3 progress

- Replaced the initial Qt direction with a lightweight pywebview shell using
  the system Edge WebView2 runtime. Qt is no longer a project dependency.
- Added a persistent desktop design system and a local-only HTML/CSS/JavaScript
  interface with batch, review, history, and settings workspaces.
- Added drag/drop integration, native file/folder dialogs, live immutable job
  events, pause/resume, cancel-remaining, output-folder access, and device/model
  status.
- The frontend loads no CDN or network resource and exposes only allow-listed
  Python methods across the bridge.
- Visual review passed at 1280 × 820 after reducing vertical density so all
  primary controls remain visible.
- A real WebView2 smoke test verifies both the complete frontend and the Python
  bridge.
