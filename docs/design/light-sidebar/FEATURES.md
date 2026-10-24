# ReverbScope 功能清单（以代码为准）· FEATURES

> 盘点基于 **main `ab3da19`**（2026-10-19 fetch，未变），对照 PR #71 `e39185c` 与 PR #89 `1ea78b3` 的 GUI。只列代码里真实存在的能力；代码里没有的写 **未实现**，设计稿里不画成可用。
> 列说明 —— **GUI(main)**：main 上的桌面界面是否已经提供（✓ 有 / CLI 仅命令行 / ✗ 无）；**#91**：本 PR 的设计稿是否覆盖（文件编号见 SPEC §18）。
> 所有设计稿里的数字、曲线、文字都由 `source/prep.py` 调这些函数在 `reverbscope demo` 合成数据上算出（见 README「数据来源」）。

## A. 测量（采集）

| # | 能力 | 源码 file:function | 输出 / 参数（单位、默认、范围） | GUI(main) | #91 |
|---|---|---|---|---|---|
| A1 | 指数正弦扫频 ESS 生成 | `core/sweep.py:generate_ess`, `measurement_signal`; `models/configuration.py:SweepSettings` | 20 Hz–20 kHz；时长默认 10 s（GUI 1–60 s）；峰值 −12 dBFS（GUI −40…0）；淡入 50 ms / 淡出 10 ms；前静音 1 s、后静音 3 s；采样率 44.1/48/88.2/96/176.4/192 kHz | ✓ | 02、03、12a |
| A2 | 独立模式（音频接口播放+录音） | `ui/pages.py:StandalonePage`; `audio/playrec.py`; `audio/portaudio.py` | 输入/输出设备、输入声道（话筒）、输出声道（扬声器）、回采声道、采样率；独立模式默认电平 −20 dBFS（`audio/backend.py:DEFAULT_STANDALONE_LEVEL_DBFS`） | ✓ | 02、02b、03、04 |
| A3 | 电平安全确认（SAFE） | `audio/backend.py:SAFE_MAX_LEVEL_DBFS = −12`; `ui/pages.py` 复选框 | 高于 −12 dBFS 必须勾选“我已调低监听音量”；`settings.save_settings` 永不保存确认 | ✓ | 03、10b |
| A4 | 双设备时钟警告 | `ui/pages.py:separate_clocks_box` | 输入、输出不是同一设备时警告，默认按钮是“不测” | ✓ | 02（就绪检查“同一设备，一个时钟”） |
| A5 | 通用 DAW 模式（4 步） | `ui/pages.py:DawModePage`, `DAW_INSTRUCTIONS`; `io/wav.py:write_sweep_file` | 步骤 1 生成测试信号 / 2 在 DAW 中录制 / 3 导入录音（录音、参考扫频、话筒声道“自动（电平最高）”、回采声道）/ 4 分析（录音配置） | ✓ | 12a、12b、12c |
| A6 | DAW 设置提示表 | `health.py:DAW_SAMPLE_RATE_SETTINGS`, `DAW_STRETCH_SETTINGS` | 各 DAW 设采样率、关时间伸缩的位置 | ✓（健康修复步骤里） | 12b |
| A7 | 导入外部脉冲响应 | `core/pipeline.py:analyze_impulse_response`; CLI `analyze-ir` | 不反卷积 | **CLI** | 不画入口（已从首页移除） |
| A8 | 测量进度 | `ui/pages.py` `QProgressBar` 0–100 | 只有百分比 | ✓ | 04 |
| A9 | 实时输入波形 / 输入电平表 / 输入预检 | — | — | **未实现** | 已从 04、02、03 移除 |
| A10 | 卷尺测量（可选） | `ui/pages.py:PlacementInputs`; `AnalysisSettings.placement_*` | 扬声器距离 m、话筒高度 m、气温 °C（未填按 20 °C） | ✓ | 03、12c（入口行） |
| A11 | 测量元数据 | `ui/pages.py` 元数据组 | 房间、位置、话筒 | ✓ | 12c |
| A12 | 回采（loopback）补偿 | `core/loopback.py:assess_loopback`, `compensate`, `path_metrics` | 声学路径延迟 ms、距离上限 m | ✓（声道选择、检查器“测量条件”） | 02、12c |
| A13 | 播放速度诊断 | `core/playback_speed.py:diagnose_playback_speed` | 生成/实测扫频速率比 | ✓（健康） | 20 |
| A14 | 演示 / 合成数据 | `demo.py:run_demo`; CLI `demo` | 合成房间 A/B；产品 GUI **没有**演示模式（`ui/measure_strip.py` 注释） | **CLI**；载入的合成会话标“合成” | 标签“合成演示数据” |

## B. 分析（算法输出）

| # | 能力 | 源码 | 输出 / 单位 | GUI(main) 视图 | #91 |
|---|---|---|---|---|---|
| B1 | 反卷积 + 直达声定位 | `core/deconvolution.py:deconvolve`, `locate_impulse_response`, `confidence_label` | 直达声置信度 高 ≥ 20 dB / 中 ≥ 10 dB / 低（峰前余量 dB） | 总览“直达声”、检查器 | 13、13b |
| B2 | 频率响应 | `core/frequency_response.py:frequency_response`; `display/curves.py` | 相对 dB；分析平滑 1/6 oct（`fr_smoothing_fraction=6`）；显示平滑选项：分析平滑 / 不平滑 / 1/48 / 1/24 / 1/12 / 1/6 / 1/3 / 1/1（`ui/views/frequency.py:SMOOTHING_CHOICES`）；电平对齐 500 Hz–2 kHz；原始曲线；差值（当前 − 基准） | 频率 | 05、05b、10 |
| B3 | 激励频带 | `core/sweep.py:excitation_band_hz` | 例：31 Hz–19.7 kHz，范围外斜线 | 频率 | 05 |
| B4 | 衰减 EDT / T20 / T30 / RT60 | `core/decay.py:analyze_decay`, `schroeder_curve`, `estimate_truncation`, `fit_decay_metric` | s；宽带 + 倍频程 63–8000 Hz；每个值带有效性（VALID / 不可靠 / 范围不足）；Lundeby 截断；曲率 %、非线性 ‰ | 衰减（频带：宽带 / 全部频带 / 单个频带；指标 EDT/T20/T30，默认 T30） | 06 |
| B4a | 单/双斜率衰减拟合（多指数 EDC 模型） | `core/multislope.py:fit_multi_slope`; `models/result.py:MultiSlopeFit`; `core/decay.py:analyze_third_octave_decay` | 每个频带：选定斜率数（1 或 2，BIC + 合理性检查）、T1/T2 s、A1/A2 dB 与能量占比 %、噪声项、转折点时间 s 与电平 dB、ΔBIC、有效性；`result.json` 的 `multi_slope`、CSV `decay_slopes.csv`（`resolution` 列：broadband / octave / third_octave）、报告“双斜率衰减”表；可选 1/3 倍频程（`--third-octave` / 测量页复选框，默认关闭）：50 Hz–10 kHz 每个 1/3 倍频程的 EDT/T20/T30 与斜率拟合，`decay.third_octave_bands`，报告“衰减斜率（1/3 倍频程）”表 | 衰减（当前频带叠加拟合曲线与两段斜率、转折点；注释行；有 1/3 倍频程时出现“频带分辨率”：倍频程 / 1/3 倍频程）、检查器“衰减斜率”（宽带）与“斜率（1/3 倍频程）” | — |
| B5 | 早晚期能量 C50 / C80 / D50 / Ts | `core/decay.py:_energy_metrics` | C50、C80 dB；D50 %；重心时间 s（显示 ms） | 总览表格 | 13、06 |
| B6 | 早期反射 + ETC | `core/reflections.py:detect_early_reflections`; `display/etc.py:etc_curve`, `marker_points` | 窗口 0.8–80 ms；阈值 −20 dB；显著度 6 dB；延迟 ms、电平 dB、超出路径 m；ETC 为检测器包络 0.1 ms 峰值保持；显示：能量-时间曲线 / 波形；范围 100 / 300 / 1000 ms / 全部 | 时间 | 14 |
| B7 | 背景噪声 | `core/noise.py:analyze_noise`, `hum_candidates` | dBFS RMS / 峰值（**未校准，不是 dB SPL**）；Welch PSD dB re FS²/Hz；倍频程电平 dBFS；交流声 50/60 Hz 谐波 | 频谱 ▸ 噪声 | 15 |
| B8 | NC / NR / dB(A) / dB SPL | `models/calibration.py`（仅保留槽位） | — | **未实现** | 15 注明未实现 |
| B9 | 低频共振候选 | `core/resonance.py:detect_potential_resonances` | ≤ 300 Hz；高出基线 dB；窄带 20 dB 衰减 vs 滤波器余振 vs 周围 | 检查器 / 报告 | 05b、07、16 |
| B10 | 房间模式计算 | — | 代码明确“不识别房间模式” | **未实现** | 不画 |
| B11 | 时频谱 | `display/timefreq.py:spectrogram`, `SpectrogramParams` | 窗口 20 ms（1–500）、步长 2 ms、时间 500 ms、频率 20–20000 Hz、电平 相对峰值/相对直达声/相对满刻度、底限 −80 dB（GUI） | 频谱 ▸ 时频谱 | 16 |
| B12 | 瀑布图（累积频谱衰减） | `display/timefreq.py:cumulative_spectral_decay`, `WaterfallParams` | 窗口 300 ms、上升 0.5 ms、步长 10 ms、切片 30（2–120）、平滑 1/12（不平滑/1/24/1/12/1/6/1/3）、立体（透视，默认开，仅显示）、底限 −60 dB、切片选择 | 频谱 ▸ 瀑布图 | 07 |
| B13 | 谐波失真 / 混叠失真 | `core/deconvolution.py:harmonic_distortion_levels`; `core/linearity.py:aliased_distortion_levels` | dB re 线性 | 健康“失真” | 20 |
| B14 | 削波 / 丢样 | `core/linearity.py:detect_clipping`, `detect_dropouts` | 峰值 dBFS、丢样次数/ms | 健康 | 20 |
| B15 | 摆位几何（垂直） | `core/placement.py:estimate_placement` | 档位 0–；扬声器高度、设备上方平面、水平间距（需卷尺距离）；声速 c=331.3√(1+T/273.15) | 房间 ▸ 摆位 | 17 |

## C. 测量健康与解读

| # | 能力 | 源码 | 输出 | GUI(main) | #91 |
|---|---|---|---|---|---|
| C1 | 测量健康（10 项） | `health.py:assess` | 参考信号、扫频、播放速度、直达声、电平、失真、采样丢失、衰减范围、本底噪声、录音长度；状态 良好/警告/无效/未知；原因、影响的指标组、下一步 | 总览、检查器 | 13、20、20b |
| C2 | 健康 → 视图跳转 | `ui/health_nav.py:view_for_check` | “显示 <视图>”按钮 | ✓ | 20（说明） |
| C3 | 分析失败指引 | `health.py:failure_guidance`, `speed_fix` | 失败原因 + 步骤 | ✓ | （SPEC §8 文本） |
| C4 | 录音配置（7 种） | `interpretation/profiles.py`; `registry.py` | 通用、人声、配音/旁白、原声吉他、鼓、房间话筒、合唱/小合奏；只改阈值和措辞 | ✓（“它看什么？”） | 01、03、09、12c |
| C5 | 解读 findings | `interpretation/interpreter.py:interpret` | 主题 + 严重度（警告/提示/信息）+ 句子 | 总览 | 13 |
| C6 | 用户类型 普通/音乐人/专业 | — | — | **未实现**（main、#71、#89 都没有） | 09 标“未实现 · 提案” |

## D. 对比、项目、房间

| # | 能力 | 源码 | 输出 | GUI(main) | #91 |
|---|---|---|---|---|---|
| D1 | 设为基准 / 清除基准 | `ui/navigator.py` 右键菜单 | 无快捷键 | ✓ | 05b（检查器“对比”） |
| D2 | 对比（有效性感知） | `core/compare.py:compare`; `models/comparison.py` | 每项 基准/对比项/差值/%/有效性；共同频带；“输入增益未变”才给有效噪声差值 | 对比（指标 / 频率响应差异 / 早期反射 / 共振 / 完整报告；互换；保存 comparison.json；复制报告） | 08 |
| D3 | 对比判定 | `interpretation/verdicts.py:judge_comparison` | 混响、清晰度、早期反射、本底噪声、低频：改善 / 大概率无关紧要 / 退化 / 证据不足 / 不可比 | ✓ | 08 |
| D4 | 项目（一个房间多位置） | `io/project_store.py`; `ui/project_view.py`; `interpretation/overview.py:summarize_project` | 位置、会话（健康、RT60、清晰度、噪声、反射、契合度）、下一步 | 项目 | 18 |
| D5 | 空间平均 + ISO 3382-2 等级 | `core/averaging.py:average_decay`, `iso_3382_2_class` | 只平均 VALID 的 EDT/T20/T30；survey/engineering/precision | 项目 | 18 |
| D6 | 房间视图（3D，QPainter） | `ui/room/view.py`, `canvas.py`, `camera.py`; `geometry/room.py`, `geometry/paths.py` | 平面图/正视/侧视、适配 F、重置视图 R、房间参数；图层：输入值 / 测量约束 / 几何假设 / 全部约束；一阶镜面预测、反射椭球、一致性检查 | 房间 | 17 |
| D7 | 导入扫描 PLY/OBJ | `geometry/scan.py:read_scan`, `place_scan`; `ui/room/scan_import.py` | 单位、上轴、偏航、偏移 | ✓ | 17（入口） |
| D8 | 示例房间 | `geometry/room.py:example_room` | 5.0 × 4.0 × 2.7 m | ✓ | 17 |

## E. 输出、文件、设置、诊断

| # | 能力 | 源码 | 说明 | GUI(main) | #91 |
|---|---|---|---|---|---|
| E1 | 文字报告 | `cli/report.py:format_report` → `cli/render.py` | 与 `reverbscope analyze` 相同；复制报告 | 报告 | 19 |
| E2 | 图表导出 PNG / SVG / CSV | `ui/plotkit.py` Export; `ui/pg.py:svg_export`, `png_export` | 每张图 | ✓ | 05… 图表行“导出 ▾” |
| E3 | 结果 CSV 导出（全部曲线与表） | `io/exporters/csv.py:export_csv`; CLI `export --format csv` | 可扩展 exporter 注册表 | **CLI** | 19 标 CLI |
| E4 | 保存/打开会话 | `io/session_store.py:save_measurement`, `load_measurement` | session.json · result.json · impulse_response.wav（可复制原始录音） | ✓ | 侧栏、工具栏 save |
| E5 | 会话打包 zip | `io/session_store.py:bundle_session`; CLI `session bundle` | 可去掉音频 | **CLI** | 19 标 CLI |
| E6 | 最近会话 | `io/recent.py` | 起始面板“已保存的会话” | ✓ | 侧栏 |
| E7 | 设置 | `settings.py:UserSettings`; `ui/settings_dialog.py` | 语言、默认配置、音频后端、默认输出文件夹、把原始录音复制进每个会话、主题（跟随系统/浅色/深色）、开发者工具 | ✓ | 09 |
| E8 | 环境报告 doctor | `diagnostics.py:environment_report`; `ui/dev_tools.py:EnvironmentReport` | 主目录脱敏 | ✓（帮助菜单） | 侧栏底“环境报告”、19 |
| E9 | 音频设备检查器 | `ui/dev_tools.py:DeviceInspector` | 开发者版 | ✓（开发者菜单） | 不画（开发者） |
| E10 | PDF / HTML 报告、一键导出全部、搜索 ⌘K、反馈入口 | — | — | **未实现** | 不画 |

## 统计

- 代码里的用户可见能力（不含 未实现 行）：**52** 项（A 12、B 13、C 5、D 8、E 9，再加 A7/A14/E3/E5 这 4 项仅 CLI 已含在内）。
- 未实现、已从设计稿去掉或只作提案标注：**8** 项（A9、B8、B10、C6、E10 中的 PDF/HTML、导出全部、搜索、反馈）。
- #91 本轮覆盖：52 项中 **50** 项有画面或入口；未画的 2 项是开发者专用的 E9 设备检查器和 C3 分析失败指引（只在 SPEC 写了文字规则）。上一轮只覆盖约 22 项。
