"""Standalone worker: only the optional runtime needs torch/numpy/OpenCV."""
from __future__ import annotations

import sys
from importlib import import_module


def main() -> None:
    import cv2
    import numpy as np
    torch = import_module("torch")

    model_path, input_path, output_path, limit = sys.argv[1:]
    inputs = np.load(input_path, allow_pickle=False)
    image, mask = inputs["image"], inputs["mask"]
    h, w = mask.shape
    scale = min(1.0, int(limit) / max(h, w))
    rw, rh = max(1, round(w * scale)), max(1, round(h * scale))
    rgb = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_AREA)
    binary = cv2.resize(mask, (rw, rh), interpolation=cv2.INTER_NEAREST)
    rgb = cv2.copyMakeBorder(rgb, 0, (-rh) % 8, 0, (-rw) % 8, cv2.BORDER_REFLECT_101)
    binary = cv2.copyMakeBorder(binary, 0, (-rh) % 8, 0, (-rw) % 8,
                                cv2.BORDER_CONSTANT, value=(0.0,))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(4)
    # Python opens Unicode Windows paths correctly; libtorch's narrow fopen does not.
    with open(model_path, "rb") as model_file:
        model = torch.jit.load(model_file, map_location=device).eval()
    image_tensor = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1)[None])).to(
        device=device, dtype=torch.float32
    ) / 255
    mask_tensor = torch.from_numpy(np.ascontiguousarray((binary > 0)[None, None])).to(
        device=device, dtype=torch.float32
    )
    with torch.inference_mode():
        output = model(image_tensor, mask_tensor)
    result = output[0].permute(1, 2, 0).cpu().numpy()[:rh, :rw]
    if not np.all(np.isfinite(result)):
        raise RuntimeError("Big-LaMa produced nonfinite pixels")
    pixels = np.clip(result * 255, 0, 255).astype(np.uint8)
    pixels = cv2.resize(pixels, (w, h), interpolation=cv2.INTER_CUBIC)
    np.save(output_path, pixels, allow_pickle=False)
    print(device)


if __name__ == "__main__":
    main()
