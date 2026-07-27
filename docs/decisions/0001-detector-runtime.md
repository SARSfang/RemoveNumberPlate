# Decision 0001: vehicle-first Paddle detector runtime

Date: 2026-07-27

## Status

Accepted for the M1 reference implementation. ONNX Runtime remains a later
packaging optimization candidate, not a prerequisite for product development.

## Context

The application must find small license plates in high-resolution automotive
photographs without asking the user to train a model. A direct whole-image pass
with the official PP-Vehicle plate detector was initially attractive because
its model archive is only about 4 MB.

The official PP-Vehicle documentation describes a two-stage process instead:
detect the vehicle, crop it, then run a PP-OCRv3 detector fine-tuned on
CCPD2019/2020. The plate detector's documented crop setting is a minimum side
length of 736 pixels.

## Evidence

Pinned official artifacts:

- PP-YOLOE-S_vehicle, archive 30,279,680 bytes, SHA-256
  `1143b3e62e1716ed056870f3788da77457b932cc7efa10b3abca5d24f61d0b2e`.
- ch_PP-OCRv3_det, archive SHA-256
  `acc7eb42b299cdb4eed2999f4de99c89555767b321c272a9878f688d24503fd9`.

On PaddleDetection's 1920 x 1280 `ppvehicleplate.jpg` example:

- direct whole-image plate detection at maximum side 960 found no plate;
- a manually supplied vehicle crop at maximum side 960 found no plate;
- the same crop at minimum side 736 found the correct plate with confidence
  0.9023;
- the implemented automatic PP-YOLOE-S vehicle-first pipeline found the plate
  at confidence 0.8941 and box `(355.94, 885.27, 540.73, 936.43)`;
- warm pipeline inference took 0.428 seconds for the 1920 x 1280 sample on an
  RTX 4060 Ti; model construction took 3.31 seconds.

## Decision

Use the official PP-YOLOE-S_vehicle detector at 640 x 640, then run the official
PP-Vehicle plate detector on each vehicle crop with `limit_type=min` and
`limit_side_len=736`.

This keeps the two model archives around 34.3 MB in total and follows the
official model contract. Users do not train or label data.

## Consequences

- Photos with multiple vehicles require one plate inference per vehicle.
- Runtime code stages Paddle model files to an ASCII-only user cache path on
  Windows because Paddle's C++ predictor cannot reliably open Chinese paths.
- Model redistribution remains a release gate because neither downloaded
  archive contains a separate weights license.
- A curated private automotive-photo benchmark is still required before
  freezing confidence thresholds.
