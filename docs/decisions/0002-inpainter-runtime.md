# Decision 0002: MI-GAN ONNX inpainting runtime

Date: 2026-07-28

## Status

Accepted for the M1 reference implementation.

## Context

The application needs an offline, pretrained inpainting model that removes a
small license-plate region without requiring users to train or label data.
Big-LaMa was the initial candidate, but the currently referenced mirror archive
is about 381 MB and the original download links are unavailable.

MI-GAN is the official ICCV 2023 implementation of a mobile-oriented
inpainting model. Its repository links a pre-converted ONNX pipeline hosted by
one of the paper's authors. The repository is MIT licensed.

## Evidence

- Artifact: `migan_pipeline_v2.onnx`
- Size: 28,079,181 bytes
- SHA-256:
  `6f1f3530a1a2324b19752018ce756088b07973cda8d7d890034ace5c8a48c40b`
- Inputs: uint8 RGB NCHW image and uint8 single-channel NCHW mask.
- The model uses 255 for known pixels and 0 for the remove region; the
  application adapter exposes the friendlier white-means-remove convention.
- On an RTX 4060 Ti workstation, ONNX Runtime CPU processed a 512 x 512 test in
  0.276 seconds, compared with 0.441 seconds for the tested GPU provider.
- On the official 1920 x 1280 vehicle sample, CPU session startup took 0.308
  seconds and end-to-end inpainting took 0.312 seconds.
- The adapter composites only selected pixels, so unmasked source pixels remain
  bit-identical in memory.

## Decision

Use the pre-converted MI-GAN 512 Places2 ONNX pipeline with ONNX Runtime CPU.
Keep vehicle and plate detection on the GPU.

This avoids a second large CUDA runtime, keeps the inpainting model around 28
MB, and provides a fast no-training path on the target workstation.

## Consequences

- The total pinned model payload is approximately 62.4 MB.
- MI-GAN may be weaker than Big-LaMa for very large removal regions, but a
  license plate is a small, bounded target.
- The final mask must be conservative; an oversized mask may remove plate
  frames or nearby bumper details.
- Visual acceptance still requires a representative private set of the user's
  automotive photographs before thresholds and mask expansion are frozen.
- Weight redistribution remains a final release review item even though the
  source repository and model page declare MIT.
