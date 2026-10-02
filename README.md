# Prompt & Dimensions from LLM

A ComfyUI custom node package created **exclusively** for the
[Qwen Image 2.1 Prompt Enhancer](https://huggingface.co/Qwen/Qwen-Image-2.1)
family. It ships two nodes: one that consumes the JSON hint the model emits and
turns it into a ready-to-use prompt plus an exact image resolution, and a standalone
dimension resolver (see below).

## Description

Qwen Image 2.1 Prompt Enhancer is a prompt-rewriting model that converts a short
image request (in any language) into a detailed English prompt and a target size.
This node consumes that output and resolves the final **width** and **height** for
the downstream image-generation node.

It is designed for both published variants:

- **Text-to-Image** — [`Qwen-Image-2.1-PE-T2I`](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-T2I):
  emits `{"rewritten_prompt": "...", "wh_ratio": "16:9"}`.
- **Image-to-Image** — [`Qwen-Image-2.1-PE-I2I`](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I):
  emits `{"rewritten_prompt": "...", "wh_ratio": "", "ratio_follow": "<image1>"}`.

In both cases `wh_ratio` and `ratio_follow` are mutually exclusive — exactly one
carries a value.

## Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/BleynChannel/ComfyUI-QwenImage-PromptExtractor.git
```

## How it works

1. Parses the JSON hint and validates the `rewritten_prompt`.
2. Resolves the size in one of two mutually exclusive ways:
   - **`wh_ratio`** + **`megapixels`** → computes width/height from the aspect
     ratio and target megapixels. The math matches ComfyUI's built-in
     **Resolution Selector** (`1 MP = 1024 × 1024`, rounded to the nearest
     multiple of `multiple`, default 8), so e.g. `1:1 @ 1 MP → 1024 × 1024`.
   - **`ratio_follow`** → copies the exact pixel size of the referenced input
     image (ignoring megapixels).
3. Emits the final `prompt`, `width`, and `height`.

If both `wh_ratio` and `ratio_follow` are present, `ratio_follow` wins.

## Inputs

| Input | Type | Description |
| --- | --- | --- |
| `llm_prompt` | String (multiline) | The JSON hint from the Qwen Image 2.1 PE model, e.g. `{"rewritten_prompt": "...", "wh_ratio": "16:9"}`. |
| `megapixels` | Float | Target size in megapixels, `0.1–16.0`. Used only with `wh_ratio`; ignored with `ratio_follow`. |
| `multiple` | Int | Grid size to round to, `8–128` (step 4, default 8). Used only with `wh_ratio`. |
| `images` | Autogrow (image) | Up to 10 reference images, keys `image0`…`image9`. `ratio_follow` may reference one of them. |

> The node is not tied to a specific generation model: it works with any
> text-to-image model set by width/height (e.g. Empty Latent Image).

## Outputs

| Output | Type | Description |
| --- | --- | --- |
| `prompt` | String | The rewritten prompt (`rewritten_prompt`). |
| `width` | Int | Image width, in pixels. |
| `height` | Int | Image height, in pixels. |

## Dimensions from Ratio (standalone)

A second node in this package that resolves image width/height **without any model**.
Provide either an aspect ratio or follow an uploaded image — the two are mutually
exclusive (at least one required; if both are present, `ratio_follow` wins).

| Input | Type | Description |
| --- | --- | --- |
| `wh_ratio` | String | Aspect ratio e.g. `16:9`. Used with `megapixels`. Mutually exclusive with `ratio_follow`. |
| `ratio_follow` | String | Reference an uploaded image's exact size, e.g. `<image1>`. Mutually exclusive with `wh_ratio`. |
| `megapixels` | Float | Target size, `0.1–16.0`. Used only with `wh_ratio` (ignored with `ratio_follow`). |
| `multiple` | Int | Grid to round to, `8–128` (step 4, default 8). Used only with `wh_ratio`. |
| `images` | Autogrow (image) | Up to 10 reference images, keys `image0`…`image9`. |

| Output | Type | Description |
| --- | --- | --- |
| `width` | Int | Image width, in pixels. |
| `height` | Int | Image height, in pixels. |

`wh_ratio` + `megapixels` computes a resolution matching ComfyUI's built-in
**Resolution Selector** (`1 MP = 1024 × 1024`, rounded to a multiple of `multiple`),
so e.g. `1:1 @ 1 MP → 1024 × 1024`. `ratio_follow` copies the referenced image's
exact pixel size. This node is not tied to a generation model: use it with any
text-to-image node that accepts width/height (e.g. Empty Latent Image).

## Resources

- 🤗 [Qwen-Image-2.1-PE-T2I](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-T2I)
- 🤗 [Qwen-Image-2.1-PE-I2I](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I)
- 🐙 [Qwen-Image-2.1 on GitHub](https://github.com/QwenLM/Qwen-Image-2.1)
- 📑 [Qwen Image 2.1 blog](https://qwen.ai/blog?id=qwen-image-2.1)

## Author

BleynChannel — <bleyn2017@gmail.com>
