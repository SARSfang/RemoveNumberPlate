# Implementation progress

Updated: 2026-07-27

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
- M2 headless pipeline: pending
- M3 batch desktop UI: pending
- M4 exception review editor: pending
- M5 Windows release candidate: pending

## Current decisions

- No user training or annotation workflow.
- Ultralytics, PyTorch, and `simple-lama-inpainting` are not production
  dependencies.
- The detector and inpainter runtimes remain undecided until M1 benchmarks.
- Model candidates remain disabled in `models/manifest.json` until their
  official artifact and SHA-256 are verified. Redistribution approval remains
  a separate release gate documented in `THIRD_PARTY_NOTICES.md`.

## M0 verification

- 35 unit tests passed; one ASCII-path staging case is skipped only because the
  repository itself is under a Chinese path.
- Ruff passes for application code, scripts, and tests.
- Strict mypy passes for all 22 checked application and script modules.
- Three integration tests pass with the pinned official models.
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
- Replaced the 381 MB Big-LaMa candidate with the official MI-GAN project's
  28,079,181-byte ONNX pipeline. SHA-256:
  `6f1f3530a1a2324b19752018ce756088b07973cda8d7d890034ace5c8a48c40b`.
- MI-GAN uses ONNX Runtime CPU: 0.276 seconds for a 512 x 512 synthetic case
  and 0.312 seconds for the 1920 x 1280 official vehicle sample. The tested GPU
  provider was slower at 0.441 seconds and would add a much larger runtime.
- Inpainting runtime decision: MI-GAN ONNX on CPU. See
  `docs/decisions/0002-inpainter-runtime.md`.
