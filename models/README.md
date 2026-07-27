# Model assets

Only `manifest.json` and this documentation are tracked by Git. Model binaries
are downloaded from verified official sources during the M1 validation stage
and are checked against a pinned SHA-256 before loading.

An entry remains disabled until its exact artifact, source URL, redistribution
terms, tensor contract, and hash have been verified.

The two enabled detector archives can be verified after download with:

```powershell
python -m scripts.verify_models
```

The production detection path uses `PP-YOLOE-S_vehicle_infer` first and passes
each vehicle crop to `ch_PP-OCRv3_det_infer`. Extract both archives directly
under this directory. Production inpainting uses OpenCV's single-file
`inpainting_lama_2025jan.onnx`; MI-GAN remains a disabled experiment after
failing visual review. Paddle model files are copied to an ASCII-only user
cache at first launch when the project path contains Chinese characters.

The model files are intentionally excluded from Git. Their official URLs and
SHA-256 values are pinned in `manifest.json`.
