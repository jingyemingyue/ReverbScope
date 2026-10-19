# ruff: noqa: E741, T201
"""Side-by-side before/after sheets. LEFT = real offscreen render of PR #71 @ e39185c,
RIGHT = design mockup (not interaction verification)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

B = Path("/workspace/work/pr71-review/before")
A = Path("/workspace/work/pr71-review/kit/out")
O = Path("/workspace/work/pr71-review/compare")
FONT = "/workspace/work/reverbscope-design/fonts/use/SourceHanSansCN-Medium.otf"
FB = "/workspace/work/reverbscope-design/fonts/use/SourceHanSansCN-Bold.otf"
PAIRS = [
    (
        "ba-01-measure-step",
        "zh_CN_1280x800_dark_measure_signal.png",
        "v2-01-measure-level.zh-dark.1440.png",
        "测量 · 第 2 步 信号与电平",
        "Measure · step 2 signal & level",
    ),
    (
        "ba-02-measuring",
        "zh_CN_1280x800_dark_measure_review.png",
        "v2-02-measuring.zh-dark.1440.png",
        "测量 · 第 3 步（前：确认页 / 后：测量进行中）",
        "Measure · step 3 (before: review / after: running)",
    ),
    (
        "ba-03-frequency",
        "zh_CN_1280x800_dark_fr.png",
        "v2-03-frequency.zh-dark.1440.png",
        "分析 · 频率响应 + 差值",
        "Analysis · frequency response + difference",
    ),
    (
        "ba-04-decay-light",
        "zh_CN_1280x800_light_decay.png",
        "v2-04-decay.zh-light.1440.png",
        "分析 · 衰减 / 分频带 RT（浅色）",
        "Analysis · decay / RT by band (light)",
    ),
    (
        "ba-05-waterfall",
        "zh_CN_1280x800_dark_waterfall.png",
        "v2-05-waterfall.zh-dark.1440.png",
        "分析 · 瀑布图",
        "Analysis · waterfall",
    ),
    (
        "ba-06-compare-light",
        "zh_CN_1280x800_light_compare.png",
        "v2-06-compare.zh-light.1440.png",
        "对比（浅色）",
        "Compare (light)",
    ),
    (
        "ba-07-narrow-960",
        "zh_CN_960x640_dark_fr.png",
        "v2-07-narrow-960.zh-dark.960.png",
        "最小窗口 960×640 · 频响",
        "Minimum window 960×640 · frequency",
    ),
    (
        "ba-08-frequency-en-light",
        "en_1280x800_light_fr.png",
        "v2-08-frequency.en-light.1440.png",
        "英文 · 浅色 · 频响（文本长度）",
        "English · light · frequency (text length)",
    ),
]
H = 760
GAP = 24
PAD = 24
HEAD = 92
LAB = 40


def fit(im, h):
    w = round(im.width * h / im.height)
    return im.resize((w, h), Image.LANCZOS)


for name, b, a, zh, en in PAIRS:
    bi = fit(Image.open(B / b).convert("RGB"), H)
    ai = fit(Image.open(A / a).convert("RGB"), H)
    W = PAD * 2 + bi.width + GAP + ai.width
    sheet = Image.new("RGB", (W, HEAD + LAB + H + PAD + 30), "#161616")
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 18), f"{zh}  ·  {en}", font=ImageFont.truetype(FB, 28), fill="#f0f0f0")
    d.text(
        (PAD, 56),
        "PR #71 设计评审 v2 · ReverbScope · 合成演示数据，非硬件实测 / synthetic demo data",
        font=ImageFont.truetype(FONT, 18),
        fill="#bdbdbd",
    )
    y = HEAD
    d.rectangle([PAD, y, PAD + bi.width, y + LAB - 6], fill="#3a3a3a")
    d.text(
        (PAD + 10, y + 4),
        "BEFORE · PR #71 @ e39185c 实际离屏渲染 (offscreen Qt, real code)",
        font=ImageFont.truetype(FB, 19),
        fill="#ffffff",
    )
    x2 = PAD + bi.width + GAP
    d.rectangle([x2, y, x2 + ai.width, y + LAB - 6], fill="#1e5f66")
    d.text(
        (x2 + 10, y + 4),
        "AFTER · 设计稿 DESIGN MOCKUP — 非交互验证 / not interaction-verified",
        font=ImageFont.truetype(FB, 19),
        fill="#ffffff",
    )
    sheet.paste(bi, (PAD, y + LAB))
    sheet.paste(ai, (x2, y + LAB))
    d.text(
        (PAD, y + LAB + H + 8),
        f"before: {b}   ·   after: {a}",
        font=ImageFont.truetype(FONT, 16),
        fill="#a6a6a6",
    )
    sheet.save(O / f"{name}.png", optimize=True)
    print(name, sheet.size)
