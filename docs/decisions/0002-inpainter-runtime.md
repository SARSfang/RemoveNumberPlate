# Decision 0002: OpenCV LaMa ONNX inpainting runtime

Date: 2026-07-28

## Status

Accepted after visual re-evaluation. The earlier MI-GAN decision is rejected.

## Context

The application must remove the complete physical plate, not merely make its
characters unreadable. It must reconstruct plausible bumper texture without
training by the user.

MI-GAN was initially selected for its 28 MB size and speed. On the official
vehicle sample it produced a conspicuous red patch, retained the blue country
strip, and had hard mask edges. Passing an inference smoke test was therefore
not sufficient evidence of usable photographic quality.

OpenCV publishes a quantized LaMa ONNX model through the Open Source Vision
Foundation account. The repository declares every file Apache-2.0.

## Evidence

- Artifact: `inpainting_lama_2025jan.onnx`
- Size: 92,591,623 bytes
- SHA-256:
  `7df918ac3921d3daf0aae1d219776cf0dc4e4935f035af81841b40adcf74fdf2`
- Inputs: float32 image `[N,3,512,512]` and white-means-remove mask
  `[N,1,512,512]`.
- The adapter runs on a square crop around the plate rather than distorting the
  entire photograph to 512 x 512.
- The text detector does not cover non-text plate parts such as a blue country
  strip, mounting shadows, and the plate frame. The default mask now expands
  by 0.95 text-box heights on the left, 1.00 on the right, and 0.40 vertically.
- A 12-pixel bidirectional feather blends inside and outside the expanded mask.
  The original plate remains inside the fully generated core, while the outer
  transition gradually returns to source pixels.
- On the 1920 x 1280 sample, CPU session startup took about 3.62 seconds and
  crop inference plus compositing took about 1.33 seconds.
- Human inspection of the close-up confirmed that the full plate was removed
  and the dark bumper and red trim continued across the removed area. MI-GAN's
  output failed the same inspection.

## Decision

Use OpenCV's quantized LaMa ONNX model on CPU with context-crop inference,
generous full-plate mask expansion, and bidirectional feathered compositing.

Keep MI-GAN in the manifest as a disabled experiment only. It must not be used
for automatic production output.

## Consequences

- Total enabled model payload is approximately 127 MB, still practical for a
  lightweight offline desktop application.
- Quality is prioritized over MI-GAN's roughly one-second speed advantage.
- A visually reviewed private automotive-photo set remains required before
  mask expansion ratios are frozen.
- Low-confidence or visually risky results must enter the exception review
  queue instead of being silently accepted.
