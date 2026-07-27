# Performance notes

Measured: 2026-07-28

These are engineering measurements on one public 1920 × 1280 sample, not a
product-wide quality or speed claim.

## Test system

- NVIDIA GeForce RTX 4060 Ti, 8 GB
- Python 3.11
- PP-YOLOE-S vehicle detector + PP-Vehicle plate detector
- OpenCV quantized LaMa inpainter
- Ten sequential source copies with verified atomic writes

Command:

```powershell
python -m scripts.benchmark_batch `
  --input testdata\public\ppvehicleplate.jpg `
  --repeats 10
```

## Runtime comparison

| Metric | Paddle GPU reference | Lightweight ONNX |
|---|---:|---:|
| Model construction | 7.75 s | 3.96 s |
| Cold first image | 2.19 s | 2.18 s |
| Warm P50 | 1.65 s | 2.38 s |
| Warm P95 | 1.72 s | 2.48 s |
| Ten-image processing | 17.14 s | 23.55 s |
| Throughput | 35.01 images/min | 25.48 images/min |
| Successful outputs | 10 / 10 | 10 / 10 |

On the public acceptance image, the original Paddle and converted ONNX
pipelines produced the same plate confidence (`0.894130`) and identical box
coordinates. The ONNX conversion does not retrain or alter the weights.

## Decision

The production build uses ONNX Runtime. Warm processing is about 27% slower on
this sample, but model construction is nearly twice as fast and the release no
longer bundles Paddle, CUDA, or cuDNN. The expanded application falls from more
than 1 GB before CUDA libraries to a few hundred MB and works without a
machine-specific AI runtime installation.

The desktop service retains one processor for the application lifetime, so
later batches reuse both detector sessions and the LaMa session. Processing
remains sequential to cap memory and preserve predictable failure isolation.
