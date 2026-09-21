"""Pure logic for resolving a diffusion prompt + target dimensions from an
LLM-generated JSON hint.

Kept free of any ``comfy``/``torch`` imports so the validation and
dimension-math logic can be unit-tested in isolation.

Expected JSON shape::

    {
        "rewritten_prompt": "...",   # ready-to-use diffusion prompt (required)
        "wh_ratio": "16:9",          # target aspect ratio (optional)
        "ratio_follow": "<image1>"   # reference an uploaded image's size (optional)
    }

``wh_ratio`` and ``ratio_follow`` are mutually exclusive: at least one must be
present and non-empty. When both are present, ``ratio_follow`` wins because it
yields an exact pixel size independent of the megapixel input.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

__all__ = [
    "PromptResolutionError",
    "parse_json_prompt",
    "extract_prompt",
    "parse_ratio",
    "dims_from_ratio",
    "resolve_follow_key",
    "resolve_dimensions",
]

# ComfyUI latent/vae grids are multiples of 8; snap resolved sizes to this.
_DIVISOR = 8
_MIN_SIZE = 8

# The LLM emits ratio_follow references strictly as '<imageN>' (1-based), e.g.
# '<image1>'. Only this exact form is accepted.
_FOLLOW_PATTERN = re.compile(r"^<image(\d+)>$")


class PromptResolutionError(ValueError):
    """Raised when the LLM hint fails validation or cannot be resolved."""


_MISSING = object()


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _get_ci(data: Mapping[str, Any], key: str) -> Any:
    """Case-insensitive lookup of ``key`` in ``data`` (falls back to exact)."""
    if key in data:
        return data[key]
    lower = key.lower()
    for k in data:
        if isinstance(k, str) and k.lower() == lower:
            return data[k]
    return _MISSING


def parse_json_prompt(text: Any) -> dict:
    """Parse and structurally validate the raw LLM hint string.

    Raises ``PromptResolutionError`` on empty input, invalid JSON, or a
    non-object JSON root.
    """
    s = _as_str(text)
    if not s:
        raise PromptResolutionError("LLM prompt is empty.")

    try:
        data = json.loads(s)
    except json.JSONDecodeError as exc:
        raise PromptResolutionError(f"LLM prompt is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise PromptResolutionError(
            "LLM prompt JSON must be an object with 'rewritten_prompt' and size fields."
        )
    return data


def extract_prompt(data: Mapping[str, Any]) -> str:
    """Return the trimmed ``rewritten_prompt`` value or raise."""
    value = _get_ci(data, "rewritten_prompt")
    if value is _MISSING:
        raise PromptResolutionError("Missing required key 'rewritten_prompt'.")
    text = _as_str(value)
    if not text:
        raise PromptResolutionError("'rewritten_prompt' is empty.")
    return text


def parse_ratio(value: Any) -> tuple[float, float] | None:
    """Parse a ``W:H`` aspect ratio into positive floats.

    The separator is always ``':'`` (e.g. ``"16:9"``); the ``"/"`` form is not
    accepted. Returns ``None`` when the value is empty (i.e. "not provided").
    Raises ``PromptResolutionError`` if malformed or non-positive.
    """
    s = _as_str(value)
    if not s:
        return None

    if ":" not in s:
        raise PromptResolutionError(
            f"wh_ratio must use a ':' separator (e.g. '16:9'), got '{value}'."
        )

    parts = s.split(":")
    if len(parts) != 2:
        raise PromptResolutionError(
            f"wh_ratio must have exactly two parts separated by ':', got '{value}'."
        )

    try:
        w = float(parts[0].strip())
        h = float(parts[1].strip())
    except ValueError as exc:
        raise PromptResolutionError(
            f"wh_ratio components must be numbers, got '{value}'."
        ) from exc

    if not (w > 0 and h > 0):
        raise PromptResolutionError(
            f"wh_ratio components must be positive, got '{value}'."
        )
    return w, h


def _round_to_grid(n: float, multiple: int, minimum: int = _MIN_SIZE) -> int:
    """Round ``n`` to the nearest multiple of ``multiple``, floored at ``minimum``.

    Mirrors ComfyUI's Resolution Selector (``comfy_extras/nodes_resolution.py``):
    ``round(n / multiple) * multiple``. Sizes not divisible by 8 cause VAE decode
    errors, so ``multiple`` defaults to 8.
    """
    return max(minimum, round(n / multiple) * multiple)


def dims_from_ratio(
    ratio_w: float, ratio_h: float, megapixels: float, multiple: int = _DIVISOR
) -> tuple[int, int]:
    """Convert an aspect ratio + megapixel target into (width, height).

    Matches ComfyUI's Resolution Selector (``comfy_extras/nodes_resolution.py``):
    the pixel budget is ``megapixels * 1024 * 1024`` (1 MP = 1024 x 1024), the
    linear scale is ``sqrt(area / (ratio_w * ratio_h))``, and each dimension is
    rounded to the nearest multiple of ``multiple`` (minimum 8).
    """
    if not megapixels > 0:
        raise PromptResolutionError(f"megapixels must be positive, got {megapixels}.")

    w_ratio, h_ratio = ratio_w, ratio_h
    total_pixels = megapixels * 1024 * 1024
    scale = math.sqrt(total_pixels / (w_ratio * h_ratio))
    width = _round_to_grid(w_ratio * scale, multiple, _MIN_SIZE)
    height = _round_to_grid(h_ratio * scale, multiple, _MIN_SIZE)
    return width, height


def resolve_follow_key(value: Any, available: Iterable[str]) -> str:
    """Map a ``ratio_follow`` reference of the form ``<imageN>`` to an actual
    uploaded-image key.

    Only the exact ``<imageN>`` form is accepted (e.g. ``<image1>``); any other
    spelling (``image1``, ``1``, ``<1>``) is rejected. ComfyUI autogrow keys
    are 0-based (``image0``..``image9``), so ``<image1>`` maps to ``image0``.
    """
    s = _as_str(value).lower()
    match = _FOLLOW_PATTERN.match(s)
    if not match:
        raise PromptResolutionError(
            "ratio_follow must be in the form '<imageN>' (e.g. '<image1>'), "
            f"got '{value}'."
        )

    try:
        idx = int(match.group(1))
    except ValueError:
        raise PromptResolutionError(
            "ratio_follow must be in the form '<imageN>' (e.g. '<image1>'), "
            f"got '{value}'."
        ) from None
    if idx < 1:
        raise PromptResolutionError(
            "ratio_follow must reference an image with a 1-based index "
            f"(e.g. '<image1>'), got '{value}'."
        )
    # ComfyUI autogrow keys are 0-based (image0..image9); the caller references
    # images 1-based (image1..image10), so translate here.
    key = f"image{idx - 1}"
    available_set = set(available)
    if key not in available_set:
        raise PromptResolutionError(
            f"ratio_follow references image{idx}, but only these images were provided: "
            f"{_format_image_labels(sorted(available_set))}."
        )
    return key


def _format_image_labels(keys: Iterable[str]) -> list[str]:
    """Relabel 0-based autogrow keys (image0..) as 1-based labels (image1..)."""
    labels: list[str] = []
    for key in keys:
        digits = key[len("image") :] if key.startswith("image") else key
        if digits.isdigit():
            try:
                labels.append(f"image{int(digits) + 1}")
            except ValueError:
                labels.append(key)
        else:
            labels.append(key)
    return labels


def _image_size(key: str, images: Mapping[str, Any]) -> tuple[int, int]:
    """Return (width, height) of an image tensor keyed ``key``.

    ComfyUI image tensors are shaped ``[B, H, W, C]``.
    """
    if key not in images:
        raise PromptResolutionError(
            f"ratio_follow references '{key}', but no such image was provided."
        )
    tensor = images[key]
    try:
        shape = tensor.shape
        height = shape[-3]
        width = shape[-2]
    except Exception as exc:  # pragma: no cover - defensive
        raise PromptResolutionError(f"Could not read dimensions of image '{key}'.") from exc
    if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        raise PromptResolutionError(
            f"Image '{key}' has invalid dimensions {width}x{height}."
        )
    return width, height


def resolve_dimensions(
    data: Mapping[str, Any],
    megapixels: float,
    images: Mapping[str, Any] | None = None,
    multiple: int = _DIVISOR,
) -> tuple[str, int, int]:
    """Resolve ``(prompt, width, height)`` from the parsed JSON.

    ``images`` maps the node's autogrow keys (``image1`` ... ``image10``,
    1-based from the caller's point of view) to image tensors.
    """
    prompt = extract_prompt(data)
    images = images or {}

    wh_raw = _get_ci(data, "wh_ratio")
    follow_raw = _get_ci(data, "ratio_follow")
    wh_present = wh_raw not in (_MISSING, None) and _as_str(wh_raw) != ""
    follow_present = follow_raw not in (_MISSING, None) and _as_str(follow_raw) != ""

    width = height = None

    if follow_present:
        key = resolve_follow_key(follow_raw, images.keys())
        width, height = _image_size(key, images)
    elif wh_present:
        ratio = parse_ratio(wh_raw)
        if ratio is None:
            raise PromptResolutionError(
                f"wh_ratio could not be parsed from '{wh_raw}'."
            )
        ratio_w, ratio_h = ratio
        width, height = dims_from_ratio(ratio_w, ratio_h, megapixels, multiple)
    else:
        raise PromptResolutionError(
            "Provide either 'wh_ratio' (e.g. '16:9') or 'ratio_follow' (e.g. '<image1>') "
            "to determine the image dimensions."
        )

    if width is None or height is None:
        raise PromptResolutionError("Failed to determine image dimensions.")
    return prompt, width, height
