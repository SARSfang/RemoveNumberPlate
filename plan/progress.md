# Implementation progress

Updated: 2026-07-28

## Environment

- Operating system: Windows 10/11 (`Windows_NT`)
- GPU: NVIDIA GeForce RTX 4060 Ti, 8188 MiB
- NVIDIA driver: 610.74
- Miniconda: 26.5.3
- Project environment: `.venv`
- Python: 3.11.9
- Environment source: python.org CPython

The system Python 3.14.2 is intentionally not used because GPU inference
packages may not provide compatible wheels.

## Milestones

- M0 engineering baseline: complete
- M1 reference model and license feasibility: complete; private-photo visual
  acceptance remains pending
- M2 headless pipeline: complete
- M3 lightweight batch desktop UI: complete
- M4 exception review editor: implementation complete; user acceptance on
  private photos remains pending
- M5 Windows release candidate: RC3 engineering in progress; external commercial
  release gates remain

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

## M4 progress

- Review-required jobs retain their detector boxes in the migrated SQLite v2
  schema. Manual edit commands are persisted as compact source-coordinate
  revisions instead of full-resolution bitmap history.
- The separate review workspace provides a thumbnail queue, large image canvas,
  rectangle, brush, eraser, remove-automatic-box, brush size, undo, redo,
  restore, wheel zoom, space-drag pan, skip, and confirm-and-reprocess actions.
- Manual reprocessing bypasses detection and reuses a lazily loaded LaMa
  session. Failed attempts keep the saved edit revision for retry.
- A real-model integration test verifies the manual-mask output path and source
  preservation.
- The editor passed a 1440 × 900 rendered visual review with the toolbar,
  queue, canvas, risk message, and primary actions visible without scrolling.

## Performance baseline

- The Paddle GPU reference measured 1.65-second warm P50 and 35.01 images/min.
- The two official Paddle detector weights were converted to ONNX opset 14
  without training. On the public acceptance image, confidence and all four
  box coordinates are identical to the Paddle reference.
- The production ONNX pipeline measures 2.38-second warm P50 and 25.48
  images/min. Construction improved from 7.75 to 3.96 seconds.
- The desktop service retains the processor across batches so construction is
  paid only once per application run.

## M5 distributable

- PyInstaller produces a Qt-free Windows onedir release using the system
  WebView2 runtime.
- Replacing Paddle/CUDA with ONNX Runtime reduced the expanded release from
  1,093.7 MiB to 336.4 MiB. The zipped v0.1.0 release is 187.2 MiB.
- The frozen executable passed an automated frontend/bridge launch check and
  completed a real public sample end to end.
- The final ZIP was extracted into a clean directory and the extracted
  executable passed the same startup check.

## RC2 release engineering

- Clean GitHub `windows-2025` run
  [30319273349](https://github.com/SARSfang/RemoveNumberPlate/actions/runs/30319273349)
  passed model reconstruction, tests, packaging, installer acceptance and
  artifact upload at commit `d7bc7f3`; the unsigned preview installer SHA-256
  is `62be0b452daf8e960060b2c267583dd702514144c43f0c408a1680160eee0047`.
- Application, package, Windows resource and installer versions are synchronized
  at `0.2.0-rc.2` by an automated test.
- Every enabled model can be rebuilt from its pinned official source. The two
  Paddle archives reproduce the checked-in-local ONNX hashes under Paddle 3.0.0,
  Paddle2ONNX 2.1.0 and opset 14; LaMa is downloaded and verified directly.
- Inno Setup 7.0.2 produces a Simplified Chinese per-user installer with
  WebView2 bootstrap, stable AppId, upgrade reuse, version metadata and future
  downgrade protection.
- RC1-to-RC2 in-place upgrade, installed desktop smoke, license/document
  presence, uninstall cleanup and user-data preservation pass.
- A frozen real-image acceptance passes at a 291-character path containing
  Chinese characters and spaces; the source SHA-256 remains unchanged.
- Runtime source contains no network-client imports and the frontend CSP blocks
  connections with `connect-src 'none'`.
- GitHub Actions can rebuild models and the Windows installer. Tagged releases
  require a PFX certificate, sign both EXE and installer, verify Authenticode,
  and only then create the GitHub Release.
- User guide, troubleshooting, privacy notice, release checklist, rotating logs
  and privacy-safe diagnostics are included.
- Remaining external gates: private-photo quality sign-off, legal review of
  Paddle weight redistribution, a Windows code-signing certificate, and an
  applicable Inno Setup commercial license.

## RC3 release hardening

- Clean GitHub `windows-2025` run
  [30320399905](https://github.com/SARSfang/RemoveNumberPlate/actions/runs/30320399905)
  passed at commit `1c77c75`; its single installer artifact reports product
  version `0.2.0.3` and SHA-256
  `a25650835501499836c1b8f86d77e86f00529de81de99069e00479377db204d3`.
- Removed the stale package-level `1.0.0` constant; package, UI, Windows
  resources and installer now resolve to `0.2.0-rc.3`.
- Batch submission is blocked when any enabled model is missing or fails its
  pinned SHA-256, and the UI disables input controls in that state.
- Each discovered batch receives a per-volume storage preflight before model
  construction, with a 512 MiB safety reserve and actionable failure message.
- Release builds delete only prior `*-Setup-v*-win64.exe` artifacts inside
  `dist/installer`, preventing wildcard uploads from mixing candidate versions.
- Local verification passed 94 tests (one documented non-ASCII skip), frozen
  packaging, installer acceptance and RC2-to-RC3 in-place upgrade with desktop
  smoke, user-data preservation and clean uninstall.
- Local RC3 installer SHA-256:
  `33bae5c65866b963b7d18cce114f5a15bcaa7601fab5681c168b511db6828852`.
