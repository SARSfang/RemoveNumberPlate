# Third-party notices

This file tracks production dependencies and model artifacts for the release
candidate. Formal commercial redistribution review remains required where
explicitly noted below.

## Python runtime dependencies

Exact versions, license metadata, and the license files shipped by each wheel
are bundled in `third_party_licenses/`. The release build collects these files
for NumPy, ONNX Runtime, OpenCV, Pillow, piexif, platformdirs, pyclipper,
pywebview, and Shapely. NumPy's bundled-library notices are preserved in its
collected license file.

## Microsoft Edge WebView2 Evergreen Bootstrapper

- Publisher: Microsoft Corporation
- Artifact: `MicrosoftEdgeWebview2Setup.exe`
- Usage: installed only when the Evergreen Runtime is absent
- Distribution documentation:
  <https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution>
- The bundled executable must retain a valid Microsoft Authenticode signature.

## Inno Setup

Inno Setup 7.0.2 is used as a build tool and is not included as an application
runtime component. The resulting installer uses its official Simplified Chinese
translation. Commercial distribution requires an applicable Inno Setup
commercial license; this remains an external release gate.

## Lucide icons

- Project: <https://lucide.dev>
- Usage: a local, release-bundled subset of interface icons under
  `app/web/assets/icons/`
- License: ISC
- Copyright: Lucide Contributors
- Runtime network access: none

## PaddleX PP-YOLOE-S vehicle detector

- Project: <https://github.com/PaddlePaddle/PaddleX>
- Runtime artifact: `ppyoloe_vehicle.onnx`
- Derived from: `PP-YOLOE-S_vehicle_infer.tar`
- Source:
  <https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-YOLOE-S_vehicle_infer.tar>
- SHA-256:
  `1143b3e62e1716ed056870f3788da77457b932cc7efa10b3abca5d24f61d0b2e`
- Project license: Apache License 2.0
- Model description: 640 x 640 single-class PP-YOLOE-S vehicle detector.
- Conversion: Paddle2ONNX 2.1.0, ONNX opset 14, no retraining.
- Release note: the downloaded model archive contains no separate license
  file. Redistribution must receive a final terms review before packaging.

## PaddleDetection PP-Vehicle plate detector

- Project: <https://github.com/PaddlePaddle/PaddleDetection>
- Pinned documentation revision:
  `b25522a0f4bde8c80603f3ba5e3472059972e3b5`
- Runtime artifact: `ppocrv3_plate.onnx`
- Derived from: `ch_PP-OCRv3_det_infer.tar.gz`
- Source:
  <https://bj.bcebos.com/v1/paddledet/models/pipeline/ch_PP-OCRv3_det_infer.tar.gz>
- SHA-256:
  `acc7eb42b299cdb4eed2999f4de99c89555767b321c272a9878f688d24503fd9`
- Project license: Apache License 2.0
- Model description: PP-OCRv3 text detector fine-tuned on a mixture of
  CCPD2019 and CCPD2020 for plate detection.
- Conversion: Paddle2ONNX 2.1.0, ONNX opset 14, no retraining.
- Release note: the downloaded model archive contains no separate license
  file. Redistribution must receive a final terms review before packaging.

## MI-GAN inpainting model

- Project: <https://github.com/Picsart-AI-Research/MI-GAN>
- Artifact: `migan_pipeline_v2.onnx`
- Source:
  <https://huggingface.co/andraniksargsyan/migan/resolve/main/migan_pipeline_v2.onnx>
- SHA-256:
  `6f1f3530a1a2324b19752018ce756088b07973cda8d7d890034ace5c8a48c40b`
- Project license: MIT
- Model description: MI-GAN 512 Places2 ONNX pipeline linked by the official
  repository and hosted by a paper author.
- Product status: rejected by visual quality review and disabled.
- Release note: redistribution must still receive a final terms review before
  packaging.

## OpenCV quantized LaMa inpainting model

- Project: <https://huggingface.co/opencv/inpainting_lama>
- Artifact: `inpainting_lama_2025jan.onnx`
- SHA-256:
  `7df918ac3921d3daf0aae1d219776cf0dc4e4935f035af81841b40adcf74fdf2`
- Publisher: Open Source Vision Foundation OpenCV account
- License: Apache License 2.0
- Product status: selected reference inpainter after visual comparison.

## PaddleOCR DB post-processing

- Project: <https://github.com/PaddlePaddle/PaddleOCR>
- Reference revision: `2661c7c0ef5c613e8f93c6e93b2e052399f0f854`
- Referenced files:
  `ppocr/data/imaug/operators.py`,
  `ppocr/postprocess/db_postprocess.py`
- License: Apache License 2.0
- Usage: the project contains an independently maintained, reduced adaptation
  of the DB resize, normalization, contour scoring, and unclip algorithms.
