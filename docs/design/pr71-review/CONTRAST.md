# 对比度检查（WCAG 2.2 AA）

文字 ≥ 4.5:1；非文字（曲线、光标、控件边框、焦点环）≥ 3:1（SC 1.4.3 / 1.4.11）。
相对亮度按 WCAG 2.x 公式计算。

## 1. PR #71 @ e39185c 现状（`ui/design/tokens.py`、`ui/workspace.py` ENTRY_COLORS）

由 `prototype/contrast_pr71_baseline.py` 的数值生成。注意：`border`/`grid` 只作分隔线时不受 1.4.11 约束，
这里列出是因为它们同时承担输入框边界和图表网格；图表网格在 `plotkit.py:340` 还被再乘 `alpha=0.15`，
实际对比度远低于表中数值。

| 主题 | 前景 | 背景 | 前景色 | 背景色 | 对比度 | 要求 | 结果 |
|---|---|---|---|---|---|---|---|
| dark | `text` | `bg` | #eeeeee | #242424 | 13.38 | 4.5 | 通过 |
| dark | `text` | `surface` | #eeeeee | #2c2c2c | 12.04 | 4.5 | 通过 |
| dark | `text` | `surface_alt` | #eeeeee | #353535 | 10.57 | 4.5 | 通过 |
| dark | `text` | `canvas` | #eeeeee | #202020 | 14.04 | 4.5 | 通过 |
| dark | `muted` | `bg` | #b7b7b7 | #242424 | 7.74 | 4.5 | 通过 |
| dark | `muted` | `surface` | #b7b7b7 | #2c2c2c | 6.96 | 4.5 | 通过 |
| dark | `muted` | `surface_alt` | #b7b7b7 | #353535 | 6.12 | 4.5 | 通过 |
| dark | `muted` | `canvas` | #b7b7b7 | #202020 | 8.12 | 4.5 | 通过 |
| dark | `accent` | `bg` | #82b4ff | #242424 | 7.33 | 4.5 | 通过 |
| dark | `accent` | `surface` | #82b4ff | #2c2c2c | 6.60 | 4.5 | 通过 |
| dark | `accent` | `surface_alt` | #82b4ff | #353535 | 5.80 | 4.5 | 通过 |
| dark | `accent` | `canvas` | #82b4ff | #202020 | 7.70 | 4.5 | 通过 |
| dark | `good` | `bg` | #91c9a1 | #242424 | 8.19 | 4.5 | 通过 |
| dark | `good` | `surface` | #91c9a1 | #2c2c2c | 7.36 | 4.5 | 通过 |
| dark | `good` | `surface_alt` | #91c9a1 | #353535 | 6.47 | 4.5 | 通过 |
| dark | `good` | `canvas` | #91c9a1 | #202020 | 8.59 | 4.5 | 通过 |
| dark | `warn` | `bg` | #efc17c | #242424 | 9.31 | 4.5 | 通过 |
| dark | `warn` | `surface` | #efc17c | #2c2c2c | 8.37 | 4.5 | 通过 |
| dark | `warn` | `surface_alt` | #efc17c | #353535 | 7.35 | 4.5 | 通过 |
| dark | `warn` | `canvas` | #efc17c | #202020 | 9.77 | 4.5 | 通过 |
| dark | `bad` | `bg` | #f3a09d | #242424 | 7.63 | 4.5 | 通过 |
| dark | `bad` | `surface` | #f3a09d | #2c2c2c | 6.87 | 4.5 | 通过 |
| dark | `bad` | `surface_alt` | #f3a09d | #353535 | 6.03 | 4.5 | 通过 |
| dark | `bad` | `canvas` | #f3a09d | #202020 | 8.01 | 4.5 | 通过 |
| dark | `info` | `bg` | #a4c6f7 | #242424 | 8.87 | 4.5 | 通过 |
| dark | `info` | `surface` | #a4c6f7 | #2c2c2c | 7.98 | 4.5 | 通过 |
| dark | `info` | `surface_alt` | #a4c6f7 | #353535 | 7.01 | 4.5 | 通过 |
| dark | `info` | `canvas` | #a4c6f7 | #202020 | 9.31 | 4.5 | 通过 |
| dark | `accent_text` | `accent` | #152033 | #82b4ff | 7.71 | 4.5 | 通过 |
| dark | `border` | `surface` | #494949 | #2c2c2c | 1.55 | 3.0 | **未通过** |
| dark | `grid` | `canvas` | #494949 | #202020 | 1.81 | 3.0 | **未通过** |
| dark | `ENTRY_COLORS[0]` | `canvas` | #177e89 | #202020 | 3.40 | 3.0 | 通过 |
| dark | `ENTRY_COLORS[1]` | `canvas` | #e07a2e | #202020 | 5.43 | 3.0 | 通过 |
| dark | `ENTRY_COLORS[2]` | `canvas` | #7a5cc7 | #202020 | 3.25 | 3.0 | 通过 |
| dark | `ENTRY_COLORS[3]` | `canvas` | #3f9c4a | #202020 | 4.71 | 3.0 | 通过 |
| dark | `ENTRY_COLORS[4]` | `canvas` | #c2437a | #202020 | 3.40 | 3.0 | 通过 |
| dark | `ENTRY_COLORS[5]` | `canvas` | #3b73c4 | #202020 | 3.44 | 3.0 | 通过 |
| dark | `ENTRY_COLORS[6]` | `canvas` | #a88a12 | #202020 | 4.90 | 3.0 | 通过 |
| dark | `ENTRY_COLORS[7]` | `canvas` | #7d8590 | #202020 | 4.37 | 3.0 | 通过 |
| light | `text` | `bg` | #262626 | #ededed | 12.93 | 4.5 | 通过 |
| light | `text` | `surface` | #262626 | #f7f7f7 | 14.13 | 4.5 | 通过 |
| light | `text` | `surface_alt` | #262626 | #e3e3e3 | 11.79 | 4.5 | 通过 |
| light | `text` | `canvas` | #262626 | #fafafa | 14.50 | 4.5 | 通过 |
| light | `muted` | `bg` | #555555 | #ededed | 6.37 | 4.5 | 通过 |
| light | `muted` | `surface` | #555555 | #f7f7f7 | 6.96 | 4.5 | 通过 |
| light | `muted` | `surface_alt` | #555555 | #e3e3e3 | 5.81 | 4.5 | 通过 |
| light | `muted` | `canvas` | #555555 | #fafafa | 7.14 | 4.5 | 通过 |
| light | `accent` | `bg` | #245d9f | #ededed | 5.71 | 4.5 | 通过 |
| light | `accent` | `surface` | #245d9f | #f7f7f7 | 6.24 | 4.5 | 通过 |
| light | `accent` | `surface_alt` | #245d9f | #e3e3e3 | 5.21 | 4.5 | 通过 |
| light | `accent` | `canvas` | #245d9f | #fafafa | 6.40 | 4.5 | 通过 |
| light | `good` | `bg` | #286b3a | #ededed | 5.51 | 4.5 | 通过 |
| light | `good` | `surface` | #286b3a | #f7f7f7 | 6.02 | 4.5 | 通过 |
| light | `good` | `surface_alt` | #286b3a | #e3e3e3 | 5.03 | 4.5 | 通过 |
| light | `good` | `canvas` | #286b3a | #fafafa | 6.18 | 4.5 | 通过 |
| light | `warn` | `bg` | #804600 | #ededed | 6.42 | 4.5 | 通过 |
| light | `warn` | `surface` | #804600 | #f7f7f7 | 7.02 | 4.5 | 通过 |
| light | `warn` | `surface_alt` | #804600 | #e3e3e3 | 5.86 | 4.5 | 通过 |
| light | `warn` | `canvas` | #804600 | #fafafa | 7.20 | 4.5 | 通过 |
| light | `bad` | `bg` | #ab302e | #ededed | 5.62 | 4.5 | 通过 |
| light | `bad` | `surface` | #ab302e | #f7f7f7 | 6.14 | 4.5 | 通过 |
| light | `bad` | `surface_alt` | #ab302e | #e3e3e3 | 5.12 | 4.5 | 通过 |
| light | `bad` | `canvas` | #ab302e | #fafafa | 6.30 | 4.5 | 通过 |
| light | `info` | `bg` | #275b9b | #ededed | 5.87 | 4.5 | 通过 |
| light | `info` | `surface` | #275b9b | #f7f7f7 | 6.41 | 4.5 | 通过 |
| light | `info` | `surface_alt` | #275b9b | #e3e3e3 | 5.35 | 4.5 | 通过 |
| light | `info` | `canvas` | #275b9b | #fafafa | 6.58 | 4.5 | 通过 |
| light | `accent_text` | `accent` | #ffffff | #245d9f | 6.68 | 4.5 | 通过 |
| light | `border` | `surface` | #c8c8c8 | #f7f7f7 | 1.56 | 3.0 | **未通过** |
| light | `grid` | `canvas` | #d6d6d6 | #fafafa | 1.39 | 3.0 | **未通过** |
| light | `ENTRY_COLORS[0]` | `canvas` | #177e89 | #fafafa | 4.59 | 3.0 | 通过 |
| light | `ENTRY_COLORS[1]` | `canvas` | #e07a2e | #fafafa | 2.88 | 3.0 | **未通过** |
| light | `ENTRY_COLORS[2]` | `canvas` | #7a5cc7 | #fafafa | 4.81 | 3.0 | 通过 |
| light | `ENTRY_COLORS[3]` | `canvas` | #3f9c4a | #fafafa | 3.32 | 3.0 | 通过 |
| light | `ENTRY_COLORS[4]` | `canvas` | #c2437a | #fafafa | 4.60 | 3.0 | 通过 |
| light | `ENTRY_COLORS[5]` | `canvas` | #3b73c4 | #fafafa | 4.54 | 3.0 | 通过 |
| light | `ENTRY_COLORS[6]` | `canvas` | #a88a12 | #fafafa | 3.19 | 3.0 | 通过 |
| light | `ENTRY_COLORS[7]` | `canvas` | #7d8590 | #fafafa | 3.57 | 3.0 | 通过 |

共 78 对，未通过 5 对。

## 2. v2 设计 token（SPEC.md §3）

由 PR #79 的 `contrast_pro.py`（162 对）在 `prototype/v2tokens.py` 覆盖后的 token 上运行生成。


| 主题 | 前景 | 背景 | 前景色 | 背景色 | 对比度 | 要求 | 用途 | 结果 |
|---|---|---|---|---|---|---|---|---|
| light | `text` | `bg` | #1f1f1f | #ededed | 14.08 | 4.5 | text | 通过 |
| light | `text` | `surface` | #1f1f1f | #fafafa | 15.79 | 4.5 | text | 通过 |
| light | `text` | `surface_alt` | #1f1f1f | #e3e3e3 | 12.84 | 4.5 | text | 通过 |
| light | `text` | `toolbar` | #1f1f1f | #e4e4e4 | 12.96 | 4.5 | text | 通过 |
| light | `text` | `sidebar` | #1f1f1f | #f0f0f0 | 14.46 | 4.5 | text | 通过 |
| light | `text` | `panel` | #1f1f1f | #f5f5f5 | 15.12 | 4.5 | text | 通过 |
| light | `text` | `hover` | #1f1f1f | #e0e0e0 | 12.49 | 4.5 | text | 通过 |
| light | `text` | `selected` | #1f1f1f | #e3f1f2 | 14.23 | 4.5 | text | 通过 |
| light | `text` | `readout_bg` | #1f1f1f | #f4f4f4 | 14.99 | 4.5 | text | 通过 |
| light | `text` | `plot_bg` | #1f1f1f | #ffffff | 16.48 | 4.5 | text | 通过 |
| light | `muted` | `bg` | #525252 | #ededed | 6.67 | 4.5 | text | 通过 |
| light | `muted` | `surface` | #525252 | #fafafa | 7.49 | 4.5 | text | 通过 |
| light | `muted` | `surface_alt` | #525252 | #e3e3e3 | 6.09 | 4.5 | text | 通过 |
| light | `muted` | `toolbar` | #525252 | #e4e4e4 | 6.15 | 4.5 | text | 通过 |
| light | `muted` | `sidebar` | #525252 | #f0f0f0 | 6.86 | 4.5 | text | 通过 |
| light | `muted` | `panel` | #525252 | #f5f5f5 | 7.17 | 4.5 | text | 通过 |
| light | `muted` | `hover` | #525252 | #e0e0e0 | 5.92 | 4.5 | text | 通过 |
| light | `muted` | `selected` | #525252 | #e3f1f2 | 6.75 | 4.5 | text | 通过 |
| light | `muted` | `readout_bg` | #525252 | #f4f4f4 | 7.10 | 4.5 | text | 通过 |
| light | `muted` | `plot_bg` | #525252 | #ffffff | 7.81 | 4.5 | text | 通过 |
| light | `faint` | `bg` | #5e5e5e | #ededed | 5.54 | 4.5 | text | 通过 |
| light | `faint` | `surface` | #5e5e5e | #fafafa | 6.21 | 4.5 | text | 通过 |
| light | `faint` | `surface_alt` | #5e5e5e | #e3e3e3 | 5.05 | 4.5 | text | 通过 |
| light | `faint` | `toolbar` | #5e5e5e | #e4e4e4 | 5.10 | 4.5 | text | 通过 |
| light | `faint` | `sidebar` | #5e5e5e | #f0f0f0 | 5.69 | 4.5 | text | 通过 |
| light | `faint` | `panel` | #5e5e5e | #f5f5f5 | 5.95 | 4.5 | text | 通过 |
| light | `faint` | `hover` | #5e5e5e | #e0e0e0 | 4.91 | 4.5 | text | 通过 |
| light | `faint` | `selected` | #5e5e5e | #e3f1f2 | 5.60 | 4.5 | text | 通过 |
| light | `faint` | `readout_bg` | #5e5e5e | #f4f4f4 | 5.90 | 4.5 | text | 通过 |
| light | `faint` | `plot_bg` | #5e5e5e | #ffffff | 6.48 | 4.5 | text | 通过 |
| light | `accent` | `surface` | #177e89 | #fafafa | 4.59 | 4.5 | text: link / active toggle | 通过 |
| light | `accent_fg` | `accent_soft` | #136a73 | #e3f1f2 | 5.43 | 4.5 | text: active tool label | 通过 |
| light | `accent_fg` | `panel` | #136a73 | #f5f5f5 | 5.77 | 4.5 | text: link in panel | 通过 |
| light | `accent_fg` | `selected` | #136a73 | #e3f1f2 | 5.43 | 4.5 | text: link in selected row | 通过 |
| light | `accent_text` | `accent` | #ffffff | #177e89 | 4.79 | 4.5 | text: primary button | 通过 |
| light | `accent_text` | `accent_hover` | #ffffff | #12656e | 6.75 | 4.5 | text: primary hover | 通过 |
| light | `accent_text` | `accent_pressed` | #ffffff | #0e5158 | 8.99 | 4.5 | text: primary pressed | 通过 |
| light | `plot_text` | `plot_bg` | #525252 | #ffffff | 7.81 | 4.5 | text: axis ticks | 通过 |
| light | `cursor_flag_text` | `cursor` | #ffffff | #1f1f1f | 16.48 | 4.5 | text: cursor flag | 通过 |
| light | `planned` | `planned_soft` | #5b4bc4 | #eeebfb | 5.51 | 4.5 | text: planned badge | 通过 |
| light | `planned` | `surface` | #5b4bc4 | #fafafa | 6.19 | 4.5 | text: planned badge on surface | 通过 |
| light | `info` | `info_soft` | #1f5fa8 | #e6eef9 | 5.51 | 4.5 | text: synthetic badge | 通过 |
| light | `good` | `good_soft` | #2e7d32 | #e8f4e9 | 4.53 | 4.5 | text: status good | 通过 |
| light | `warn` | `warn_soft` | #9a5b00 | #fdf1de | 4.86 | 4.5 | text: status warning | 通过 |
| light | `bad` | `bad_soft` | #c62828 | #fbe9e9 | 4.80 | 4.5 | text: status critical | 通过 |
| light | `info` | `surface` | #1f5fa8 | #fafafa | 6.17 | 4.5 | text: info | 通过 |
| light | `good` | `panel` | #2e7d32 | #f5f5f5 | 4.70 | 4.5 | text: good in panel | 通过 |
| light | `warn` | `panel` | #9a5b00 | #f5f5f5 | 4.98 | 4.5 | text: warn in panel | 通过 |
| light | `warn` | `surface` | #9a5b00 | #fafafa | 5.20 | 4.5 | text: warn in table | 通过 |
| light | `bad` | `surface` | #c62828 | #fafafa | 5.39 | 4.5 | text: error | 通过 |
| light | `border_strong` | `surface` | #8a8a8a | #fafafa | 3.31 | 3.0 | non-text: input outline | 通过 |
| light | `border_strong` | `panel` | #8a8a8a | #f5f5f5 | 3.17 | 3.0 | non-text: input outline in panel | 通过 |
| light | `focus` | `surface` | #177e89 | #fafafa | 4.59 | 3.0 | non-text: focus ring | 通过 |
| light | `focus` | `toolbar` | #177e89 | #e4e4e4 | 3.77 | 3.0 | non-text: focus ring on toolbar | 通过 |
| light | `accent` | `toolbar` | #177e89 | #e4e4e4 | 3.77 | 3.0 | non-text: active icon on toolbar | 通过 |
| light | `cursor` | `plot_bg` | #1f1f1f | #ffffff | 16.48 | 3.0 | non-text: cursor line | 通过 |
| light | `plot_axis` | `plot_bg` | #8a8a8a | #ffffff | 3.45 | 3.0 | non-text: axis line | 通过 |
| light | `band_1` | `plot_bg` | #440154 | #ffffff | 15.24 | 3.0 | non-text: band curve | 通过 |
| light | `series_1` | `plot_bg` | #177e89 | #ffffff | 4.79 | 3.0 | non-text: curve | 通过 |
| light | `series_1` | `surface` | #177e89 | #fafafa | 4.59 | 3.0 | non-text: legend swatch | 通过 |
| light | `band_2` | `plot_bg` | #472f7d | #ffffff | 10.66 | 3.0 | non-text: band curve | 通过 |
| light | `series_2` | `plot_bg` | #d9731f | #ffffff | 3.27 | 3.0 | non-text: curve | 通过 |
| light | `series_2` | `surface` | #d9731f | #fafafa | 3.13 | 3.0 | non-text: legend swatch | 通过 |
| light | `band_3` | `plot_bg` | #39558c | #ffffff | 7.36 | 3.0 | non-text: band curve | 通过 |
| light | `series_3` | `plot_bg` | #6b5bd2 | #ffffff | 5.18 | 3.0 | non-text: curve | 通过 |
| light | `series_3` | `surface` | #6b5bd2 | #fafafa | 4.97 | 3.0 | non-text: legend swatch | 通过 |
| light | `band_4` | `plot_bg` | #2a778e | #ffffff | 5.09 | 3.0 | non-text: band curve | 通过 |
| light | `series_4` | `plot_bg` | #2f9e57 | #ffffff | 3.42 | 3.0 | non-text: curve | 通过 |
| light | `series_4` | `surface` | #2f9e57 | #fafafa | 3.27 | 3.0 | non-text: legend swatch | 通过 |
| light | `band_5` | `plot_bg` | #1f968b | #ffffff | 3.62 | 3.0 | non-text: band curve | 通过 |
| light | `series_5` | `plot_bg` | #c2417e | #ffffff | 4.83 | 3.0 | non-text: curve | 通过 |
| light | `series_5` | `surface` | #c2417e | #fafafa | 4.62 | 3.0 | non-text: legend swatch | 通过 |
| light | `band_6` | `plot_bg` | #2da670 | #ffffff | 3.09 | 3.0 | non-text: band curve | 通过 |
| light | `series_6` | `plot_bg` | #8c6d1f | #ffffff | 4.86 | 3.0 | non-text: curve | 通过 |
| light | `series_6` | `surface` | #8c6d1f | #fafafa | 4.65 | 3.0 | non-text: legend swatch | 通过 |
| light | `band_7` | `plot_bg` | #4ba62e | #ffffff | 3.09 | 3.0 | non-text: band curve | 通过 |
| light | `series_7` | `plot_bg` | #3b82c4 | #ffffff | 4.06 | 3.0 | non-text: curve | 通过 |
| light | `series_7` | `surface` | #3b82c4 | #fafafa | 3.89 | 3.0 | non-text: legend swatch | 通过 |
| light | `band_8` | `plot_bg` | #899a15 | #ffffff | 3.14 | 3.0 | non-text: band curve | 通过 |
| light | `series_8` | `plot_bg` | #6b7280 | #ffffff | 4.83 | 3.0 | non-text: curve | 通过 |
| light | `series_8` | `surface` | #6b7280 | #fafafa | 4.63 | 3.0 | non-text: legend swatch | 通过 |
| dark | `text` | `bg` | #eeeeee | #242424 | 13.38 | 4.5 | text | 通过 |
| dark | `text` | `surface` | #eeeeee | #2c2c2c | 12.04 | 4.5 | text | 通过 |
| dark | `text` | `surface_alt` | #eeeeee | #363636 | 10.42 | 4.5 | text | 通过 |
| dark | `text` | `toolbar` | #eeeeee | #2c2c2c | 12.04 | 4.5 | text | 通过 |
| dark | `text` | `sidebar` | #eeeeee | #272727 | 12.88 | 4.5 | text | 通过 |
| dark | `text` | `panel` | #eeeeee | #272727 | 12.88 | 4.5 | text | 通过 |
| dark | `text` | `hover` | #eeeeee | #383838 | 10.11 | 4.5 | text | 通过 |
| dark | `text` | `selected` | #eeeeee | #1e3a3e | 10.46 | 4.5 | text | 通过 |
| dark | `text` | `readout_bg` | #eeeeee | #202020 | 14.04 | 4.5 | text | 通过 |
| dark | `text` | `plot_bg` | #eeeeee | #1b1b1b | 14.85 | 4.5 | text | 通过 |
| dark | `muted` | `bg` | #b7b7b7 | #242424 | 7.74 | 4.5 | text | 通过 |
| dark | `muted` | `surface` | #b7b7b7 | #2c2c2c | 6.96 | 4.5 | text | 通过 |
| dark | `muted` | `surface_alt` | #b7b7b7 | #363636 | 6.03 | 4.5 | text | 通过 |
| dark | `muted` | `toolbar` | #b7b7b7 | #2c2c2c | 6.96 | 4.5 | text | 通过 |
| dark | `muted` | `sidebar` | #b7b7b7 | #272727 | 7.45 | 4.5 | text | 通过 |
| dark | `muted` | `panel` | #b7b7b7 | #272727 | 7.45 | 4.5 | text | 通过 |
| dark | `muted` | `hover` | #b7b7b7 | #383838 | 5.85 | 4.5 | text | 通过 |
| dark | `muted` | `selected` | #b7b7b7 | #1e3a3e | 6.05 | 4.5 | text | 通过 |
| dark | `muted` | `readout_bg` | #b7b7b7 | #202020 | 8.12 | 4.5 | text | 通过 |
| dark | `muted` | `plot_bg` | #b7b7b7 | #1b1b1b | 8.59 | 4.5 | text | 通过 |
| dark | `faint` | `bg` | #a6a6a6 | #242424 | 6.38 | 4.5 | text | 通过 |
| dark | `faint` | `surface` | #a6a6a6 | #2c2c2c | 5.74 | 4.5 | text | 通过 |
| dark | `faint` | `surface_alt` | #a6a6a6 | #363636 | 4.96 | 4.5 | text | 通过 |
| dark | `faint` | `toolbar` | #a6a6a6 | #2c2c2c | 5.74 | 4.5 | text | 通过 |
| dark | `faint` | `sidebar` | #a6a6a6 | #272727 | 6.14 | 4.5 | text | 通过 |
| dark | `faint` | `panel` | #a6a6a6 | #272727 | 6.14 | 4.5 | text | 通过 |
| dark | `faint` | `hover` | #a6a6a6 | #383838 | 4.82 | 4.5 | text | 通过 |
| dark | `faint` | `selected` | #a6a6a6 | #1e3a3e | 4.99 | 4.5 | text | 通过 |
| dark | `faint` | `readout_bg` | #a6a6a6 | #202020 | 6.69 | 4.5 | text | 通过 |
| dark | `faint` | `plot_bg` | #a6a6a6 | #1b1b1b | 7.08 | 4.5 | text | 通过 |
| dark | `accent` | `surface` | #4fb6c3 | #2c2c2c | 5.86 | 4.5 | text: link / active toggle | 通过 |
| dark | `accent_fg` | `accent_soft` | #6cc6d1 | #1e3a3e | 6.15 | 4.5 | text: active tool label | 通过 |
| dark | `accent_fg` | `panel` | #6cc6d1 | #272727 | 7.57 | 4.5 | text: link in panel | 通过 |
| dark | `accent_fg` | `selected` | #6cc6d1 | #1e3a3e | 6.15 | 4.5 | text: link in selected row | 通过 |
| dark | `accent_text` | `accent` | #0b1114 | #4fb6c3 | 7.98 | 4.5 | text: primary button | 通过 |
| dark | `accent_text` | `accent_hover` | #0b1114 | #6cc6d1 | 9.63 | 4.5 | text: primary hover | 通过 |
| dark | `accent_text` | `accent_pressed` | #0b1114 | #3a9aa6 | 5.75 | 4.5 | text: primary pressed | 通过 |
| dark | `plot_text` | `plot_bg` | #b7b7b7 | #1b1b1b | 8.59 | 4.5 | text: axis ticks | 通过 |
| dark | `cursor_flag_text` | `cursor` | #1b1b1b | #eeeeee | 14.85 | 4.5 | text: cursor flag | 通过 |
| dark | `planned` | `planned_soft` | #a99cf0 | #2a2640 | 6.00 | 4.5 | text: planned badge | 通过 |
| dark | `planned` | `surface` | #a99cf0 | #2c2c2c | 5.79 | 4.5 | text: planned badge on surface | 通过 |
| dark | `info` | `info_soft` | #7fb2ee | #1a2a3d | 6.59 | 4.5 | text: synthetic badge | 通过 |
| dark | `good` | `good_soft` | #6cc070 | #1b2e1e | 6.46 | 4.5 | text: status good | 通过 |
| dark | `warn` | `warn_soft` | #f0b35a | #352915 | 7.64 | 4.5 | text: status warning | 通过 |
| dark | `bad` | `bad_soft` | #ef6a6a | #3a1d1d | 5.05 | 4.5 | text: status critical | 通过 |
| dark | `info` | `surface` | #7fb2ee | #2c2c2c | 6.32 | 4.5 | text: info | 通过 |
| dark | `good` | `panel` | #6cc070 | #272727 | 6.69 | 4.5 | text: good in panel | 通过 |
| dark | `warn` | `panel` | #f0b35a | #272727 | 8.04 | 4.5 | text: warn in panel | 通过 |
| dark | `warn` | `surface` | #f0b35a | #2c2c2c | 7.52 | 4.5 | text: warn in table | 通过 |
| dark | `bad` | `surface` | #ef6a6a | #2c2c2c | 4.62 | 4.5 | text: error | 通过 |
| dark | `border_strong` | `surface` | #7a7a7a | #2c2c2c | 3.25 | 3.0 | non-text: input outline | 通过 |
| dark | `border_strong` | `panel` | #7a7a7a | #272727 | 3.48 | 3.0 | non-text: input outline in panel | 通过 |
| dark | `focus` | `surface` | #4fb6c3 | #2c2c2c | 5.86 | 3.0 | non-text: focus ring | 通过 |
| dark | `focus` | `toolbar` | #4fb6c3 | #2c2c2c | 5.86 | 3.0 | non-text: focus ring on toolbar | 通过 |
| dark | `accent` | `toolbar` | #4fb6c3 | #2c2c2c | 5.86 | 3.0 | non-text: active icon on toolbar | 通过 |
| dark | `cursor` | `plot_bg` | #eeeeee | #1b1b1b | 14.85 | 3.0 | non-text: cursor line | 通过 |
| dark | `plot_axis` | `plot_bg` | #6e6e6e | #1b1b1b | 3.38 | 3.0 | non-text: axis line | 通过 |
| dark | `band_1` | `plot_bg` | #5a68ba | #1b1b1b | 3.38 | 3.0 | non-text: band curve | 通过 |
| dark | `series_1` | `plot_bg` | #4fb6c3 | #1b1b1b | 7.23 | 3.0 | non-text: curve | 通过 |
| dark | `series_1` | `surface` | #4fb6c3 | #2c2c2c | 5.86 | 3.0 | non-text: legend swatch | 通过 |
| dark | `band_2` | `plot_bg` | #3a74a0 | #1b1b1b | 3.43 | 3.0 | non-text: band curve | 通过 |
| dark | `series_2` | `plot_bg` | #f29a52 | #1b1b1b | 7.81 | 3.0 | non-text: curve | 通过 |
| dark | `series_2` | `surface` | #f29a52 | #2c2c2c | 6.33 | 3.0 | non-text: legend swatch | 通过 |
| dark | `band_3` | `plot_bg` | #26828e | #1b1b1b | 3.83 | 3.0 | non-text: band curve | 通过 |
| dark | `series_3` | `plot_bg` | #9c8fea | #1b1b1b | 6.18 | 3.0 | non-text: curve | 通过 |
| dark | `series_3` | `surface` | #9c8fea | #2c2c2c | 5.01 | 3.0 | non-text: legend swatch | 通过 |
| dark | `band_4` | `plot_bg` | #1e9d89 | #1b1b1b | 5.12 | 3.0 | non-text: band curve | 通过 |
| dark | `series_4` | `plot_bg` | #5bc07f | #1b1b1b | 7.62 | 3.0 | non-text: curve | 通过 |
| dark | `series_4` | `surface` | #5bc07f | #2c2c2c | 6.18 | 3.0 | non-text: legend swatch | 通过 |
| dark | `band_5` | `plot_bg` | #35b779 | #1b1b1b | 6.73 | 3.0 | non-text: band curve | 通过 |
| dark | `series_5` | `plot_bg` | #e07aaa | #1b1b1b | 6.18 | 3.0 | non-text: curve | 通过 |
| dark | `series_5` | `surface` | #e07aaa | #2c2c2c | 5.01 | 3.0 | non-text: legend swatch | 通过 |
| dark | `band_6` | `plot_bg` | #6ccd5a | #1b1b1b | 8.63 | 3.0 | non-text: band curve | 通过 |
| dark | `series_6` | `plot_bg` | #c7a34a | #1b1b1b | 7.19 | 3.0 | non-text: curve | 通过 |
| dark | `series_6` | `surface` | #c7a34a | #2c2c2c | 5.83 | 3.0 | non-text: legend swatch | 通过 |
| dark | `band_7` | `plot_bg` | #b4de2c | #1b1b1b | 11.01 | 3.0 | non-text: band curve | 通过 |
| dark | `series_7` | `plot_bg` | #79aee3 | #1b1b1b | 7.36 | 3.0 | non-text: curve | 通过 |
| dark | `series_7` | `surface` | #79aee3 | #2c2c2c | 5.97 | 3.0 | non-text: legend swatch | 通过 |
| dark | `band_8` | `plot_bg` | #fde725 | #1b1b1b | 13.64 | 3.0 | non-text: band curve | 通过 |
| dark | `series_8` | `plot_bg` | #9ca3af | #1b1b1b | 6.78 | 3.0 | non-text: curve | 通过 |
| dark | `series_8` | `surface` | #9ca3af | #2c2c2c | 5.50 | 3.0 | non-text: legend swatch | 通过 |

共 162 对，未通过 0 对。
