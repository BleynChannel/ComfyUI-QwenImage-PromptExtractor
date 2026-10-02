import sys

sys.path.insert(0, "/mnt/AI/ComfyUI/configs/linux/custom_nodes/ComfyUI-QwenImage-PromptExtractor")

import resolver as r


class FakeImg:
    def __init__(self, h, w):
        self.shape = (1, h, w, 3)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    assert cond, name


def expect_error(name, fn):
    try:
        fn()
    except r.PromptResolutionError:
        print("PASS (raised):", name)
        return
    raise AssertionError(f"{name}: expected PromptResolutionError, none raised")


# 1. Happy path: wh_ratio + megapixels
prompt, w, h = r.resolve_dimensions(
    {"rewritten_prompt": "a cat", "wh_ratio": "16:9"}, 1.0
)
check("wh_ratio 16:9 @1MP", (w, h) == (1368, 768))
check("prompt passthrough", prompt == "a cat")

# 2. 1:1 @1MP -> exactly 1024x1024 (1 MP = 1024x1024, matches Resolution Selector)
_, w, h = r.resolve_dimensions({"rewritten_prompt": "x", "wh_ratio": "1:1"}, 1.0)
check("1:1 @1MP", (w, h) == (1024, 1024))

# 3. ratio_follow uses exact image size, ignoring megapixels.
# Reference is 1-based (image1); ComfyUI autogrow keys are 0-based (image0).
imgs = {"image0": FakeImg(1024, 1024)}
_, w, h = r.resolve_dimensions(
    {"rewritten_prompt": "x", "ratio_follow": "<image1>"}, 5.0, imgs
)
check("ratio_follow <image1> ignores MP", (w, h) == (1024, 1024))

# 4. ratio_follow with '<image3>' -> actual key image2, landscape image
imgs = {"image2": FakeImg(768, 1344)}
_, w, h = r.resolve_dimensions(
    {"rewritten_prompt": "x", "ratio_follow": "<image3>"}, 1.0, imgs
)
check("ratio_follow <image3>", (w, h) == (1344, 768))

# 5. both present -> follow wins (image2 -> actual image1)
imgs = {"image1": FakeImg(640, 480)}
_, w, h = r.resolve_dimensions(
    {"rewritten_prompt": "x", "wh_ratio": "1:1", "ratio_follow": "<image2>"},
    1.0, imgs,
)
check("follow wins over wh_ratio", (w, h) == (480, 640))

# 6. case-insensitive keys (4:3 @0.5MP, rounded to nearest 8-grid)
_, w, h = r.resolve_dimensions(
    {"REWRITTEN_PROMPT": "hi", "WH_RATIO": "4:3"}, 0.5
)
check("case-insensitive keys", (w, h) == (840, 624))

# --- validation errors (JSON-level, via parse_json_prompt) ---
expect_error("empty prompt", lambda: r.parse_json_prompt("   "))
expect_error("invalid json", lambda: r.parse_json_prompt("not json"))
expect_error("json not object", lambda: r.parse_json_prompt("[1,2,3]"))

# --- validation errors (resolution-level, via resolve_dimensions) ---
expect_error("missing rewritten_prompt", lambda: r.resolve_dimensions({"wh_ratio": "1:1"}, 1.0))
expect_error("no size fields", lambda: r.resolve_dimensions({"rewritten_prompt": "x"}, 1.0))
expect_error("bad ratio sep", lambda: r.resolve_dimensions({"rewritten_prompt": "x", "wh_ratio": "169"}, 1.0))
expect_error("non-positive ratio", lambda: r.resolve_dimensions({"rewritten_prompt": "x", "wh_ratio": "0:9"}, 1.0))
expect_error("follow missing image", lambda: r.resolve_dimensions({"rewritten_prompt": "x", "ratio_follow": "<image9>"}, 1.0, {"image0": FakeImg(100, 100)}))
expect_error("follow non-numeric", lambda: r.resolve_dimensions({"rewritten_prompt": "x", "ratio_follow": "<abc>"}, 1.0, {"image1": FakeImg(100, 100)}))
# strict '<imageN>' only: reject forms without angle brackets / 'image' prefix
expect_error("reject 'image1' no brackets", lambda: r.resolve_dimensions(
    {"rewritten_prompt": "x", "ratio_follow": "image1"}, 1.0, {"image0": FakeImg(512, 384)}
))
expect_error("reject '<1>' no image prefix", lambda: r.resolve_dimensions(
    {"rewritten_prompt": "x", "ratio_follow": "<1>"}, 1.0, {"image0": FakeImg(512, 384)}
))
expect_error("bad megapixels", lambda: r.resolve_dimensions({"rewritten_prompt": "x", "wh_ratio": "1:1"}, 0))

# --- enhancements: 1-based image refs, W/H rejection, custom multiple ---
# image0 is a valid 0-based autogrow key (reference image1 -> image0)
_, w, h = r.resolve_dimensions(
    {"rewritten_prompt": "x", "ratio_follow": "<image1>"}, 1.0, {"image0": FakeImg(512, 384)}
)
check("image1 -> actual image0", (w, h) == (384, 512))

# 1-based: reference image0 is invalid (must be >= 1)
expect_error("image0 reference invalid", lambda: r.resolve_dimensions(
    {"rewritten_prompt": "x", "ratio_follow": "<image0>"}, 1.0, {"image0": FakeImg(512, 384)}
))

# wh_ratio must use ':' not '/'
expect_error("wh_ratio rejects '/'", lambda: r.resolve_dimensions(
    {"rewritten_prompt": "x", "wh_ratio": "16/9"}, 1.0
))

# custom 'multiple' rounds to nearest multiple (1:1 @1MP, multiple=16 -> 1024)
_, w, h = r.resolve_dimensions(
    {"rewritten_prompt": "x", "wh_ratio": "1:1"}, 1.0, None, multiple=16
)
check("multiple=16 rounds to nearest", (w, h) == (1024, 1024))

# --- regression: output must match ComfyUI Resolution Selector exactly ---
# comfy_extras/nodes_resolution.py: total = mp*1024*1024, dim = round(dim/multiple)*multiple
MATCH_RS = [
    ((1.0, "1:1", 8), (1024, 1024)),
    ((1.0, "16:9", 8), (1368, 768)),
    ((1.0, "4:3", 8), (1184, 888)),
    ((0.5, "4:3", 8), (840, 624)),
]
for (mp, ratio, mult), exp in MATCH_RS:
    _, w, h = r.resolve_dimensions(
        {"rewritten_prompt": "x", "wh_ratio": ratio}, mp, None, multiple=mult
    )
    check(f"matches Resolution Selector {ratio} @{mp}MP", (w, h) == exp)

# --- resolve_resolution: (wh_ratio | ratio_follow) -> (width, height) ---
# wh_ratio + megapixels (no images, no follow)
w, h = r.resolve_resolution("16:9", "", 1.0, None)
check("wh_ratio 16:9 @1MP", (w, h) == (1368, 768))

# 1:1 @1MP -> exactly 1024x1024 (matches Resolution Selector)
w, h = r.resolve_resolution("1:1", "", 1.0, None)
check("wh_ratio 1:1 @1MP", (w, h) == (1024, 1024))

# ratio_follow reuses an uploaded image's exact size (1-based -> 0-based key)
w, h = r.resolve_resolution("", "<image1>", 5.0, {"image0": FakeImg(1024, 1024)})
check("ratio_follow <image1> ignores MP", (w, h) == (1024, 1024))

# follow reference image2 -> actual image1
w, h = r.resolve_resolution("", "<image2>", 1.0, {"image1": FakeImg(768, 1344)})
check("ratio_follow <image2> -> image1", (w, h) == (1344, 768))

# both present -> follow wins (exact size, MP ignored)
# FakeImg(h, w): h=320, w=240 -> (width, height) = (240, 320)
w, h = r.resolve_resolution("4:3", "<image1>", 99.0, {"image0": FakeImg(320, 240)})
check("both present -> follow wins", (w, h) == (240, 320))

# custom 'multiple' rounds to nearest multiple (1:1 @1MP, multiple=16 -> 1024)
w, h = r.resolve_resolution("1:1", "", 1.0, None, multiple=16)
check("multiple=16 rounds to nearest", (w, h) == (1024, 1024))

# neither provided -> error
expect_error("neither provided", lambda: r.resolve_resolution("", "", 1.0, None))

# empty strings count as not provided -> error
expect_error("empty strings", lambda: r.resolve_resolution("", "", 1.0, None))

# wh_ratio rejects '/'
expect_error("wh_ratio rejects '/'", lambda: r.resolve_resolution("16/9", "", 1.0, None))

# non-positive ratio
expect_error("non-positive ratio", lambda: r.resolve_resolution("0:9", "", 1.0, None))

# follow missing image
expect_error("follow missing image", lambda: r.resolve_resolution(
    "", "<image9>", 1.0, {"image0": FakeImg(100, 100)}))

# follow non-numeric
expect_error("follow non-numeric", lambda: r.resolve_resolution(
    "", "<abc>", 1.0, {"image0": FakeImg(100, 100)}))

# reject 'image1' no brackets
expect_error("reject 'image1' no brackets", lambda: r.resolve_resolution(
    "", "image1", 1.0, {"image0": FakeImg(512, 384)}))

# reject '<1>' no image prefix
expect_error("reject '<1>' no image prefix", lambda: r.resolve_resolution(
    "", "<1>", 1.0, {"image0": FakeImg(512, 384)}))

# bad megapixels
expect_error("bad megapixels", lambda: r.resolve_resolution("1:1", "", 0, None))

print("\nALL TESTS PASSED")
