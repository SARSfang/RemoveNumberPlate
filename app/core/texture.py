"""Conservative transfer of real neighbouring high-frequency texture."""
from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray


def enhance_texture(
    original: NDArray[np.uint8],
    generated: NDArray[np.uint8],
    mask: NDArray[np.uint8],
    excluded: NDArray[np.uint8],
    strength: float,
) -> tuple[NDArray[np.uint8], str]:
    """Borrow residual detail only from comparable, low-gradient neighbour patches."""
    if strength <= 0 or not np.any(mask):
        return generated, "disabled"
    points = cv2.findNonZero((mask > 0).astype(np.uint8))
    x, y, w, h = cv2.boundingRect(points)
    height, width = mask.shape
    # Only full-size, unmasked neighbouring patches are candidates; no tiled noise.
    candidates = [(x-w, y), (x+w, y), (x, y-h), (x, y+h)]
    target = generated[y:y+h, x:x+w].astype(np.float32)
    selected = mask[y:y+h, x:x+w] > 0
    target_mean = target[selected].mean(axis=0)
    target_gray = cv2.cvtColor(target, cv2.COLOR_RGB2GRAY)
    target_grad = cv2.magnitude(cv2.Sobel(target_gray, cv2.CV_32F, 1, 0),
                               cv2.Sobel(target_gray, cv2.CV_32F, 0, 1))
    if np.percentile(target_grad[selected], 95) > 45:
        return generated, "structural_edge"
    best: tuple[float, NDArray[np.float32]] | None = None
    for sx, sy in candidates:
        if sx < 0 or sy < 0 or sx+w > width or sy+h > height:
            continue
        if np.any(excluded[sy:sy+h, sx:sx+w]):
            continue
        patch = original[sy:sy+h, sx:sx+w].astype(np.float32)
        difference = float(np.linalg.norm(patch.mean(axis=(0, 1)) - target_mean))
        if difference > 25:
            continue
        gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
        gradient = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0),
                                cv2.Sobel(gray, cv2.CV_32F, 0, 1))
        if np.percentile(gradient, 95) > 45:
            continue
        residual = patch - cv2.GaussianBlur(patch, (0, 0), 1.2)
        energy = float(np.std(residual))
        if not 0.6 <= energy <= 6:
            continue
        if best is None or difference < best[0]:
            best = difference, residual
    if best is None:
        return generated, "no_matching_texture"
    distance = cv2.distanceTransform(selected.astype(np.uint8), cv2.DIST_L2, 3)
    weight = np.minimum(distance / 6, 1)[:, :, None] * strength
    result = generated.copy()
    enhanced = np.rint(np.clip(target + np.clip(best[1], -8, 8) * weight, 0, 255)).astype(np.uint8)
    crop = result[y:y+h, x:x+w]
    crop[selected] = enhanced[selected]
    return result, "applied"
