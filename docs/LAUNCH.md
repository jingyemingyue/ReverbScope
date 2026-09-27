# Launch copy

Ready-to-use text for announcing RoomScope. The tone throughout: built by a
developer, open source, asking for feedback, upfront about what is not done.
Before posting anywhere, check that the facts still hold (version, "no
hardware results yet", "not on PyPI"), and read the community's current
rules: several audio subreddits allow self-promotion only in specific threads
or on specific days.

Link to use: `https://github.com/jingyemingyue/RoomScope`

## 1. GitHub tagline

> DAW-independent room acoustics analyzer for recording engineers. Measure RT60, early reflections, frequency response and noise floor, and compare microphone positions.

## 2. One-line introduction

> RoomScope is an open-source tool that measures your recording room through your own DAW and tells you what a microphone position is picking up.

## 3. 50-word description

> RoomScope is an open-source room acoustics analyzer for people who record.
> It generates a sine-sweep WAV, you play and record it in any DAW, and it
> reports reverberation (RT60), early reflections, frequency response, noise
> floor and low-frequency resonances, then compares two microphone positions.
> CLI, desktop app and Python API. Alpha; feedback welcome.

## 4. 150-word description

> RoomScope is an open-source (Apache-2.0) room acoustics analyzer built
> around one question recording engineers ask all the time: is this a good
> place to put the microphone?
>
> It works with the DAW you already use. RoomScope writes a sine-sweep test
> signal; you play it through your monitors and record the microphone in
> your DAW; RoomScope finds the sweep in the exported WAV and reports
> reverberation (EDT, T20, T30, RT60 per octave band), early reflections with
> their delays and levels, frequency response, noise floor and mains hum, and
> potential low-frequency resonances. Save two positions and compare them.
>
> Every number carries a validity flag. When the data is not good enough,
> RoomScope says so instead of guessing, and there is no "room score".
>
> It runs as a command-line tool, a Qt desktop app and a Python library.
> `roomscope demo` shows the whole workflow on a simulated room without any
> hardware. It is alpha software: the synthetic tests pass, and real-hardware
> reports are the thing it needs most.

## 5. Reddit: r/audioengineering

**Title:** I built an open-source tool to compare mic positions using your own DAW (looking for testers)

> Hi all. I have been working on RoomScope, an open-source tool for a
> question I kept asking myself when setting up vocals and acoustic guitar
> at home: is this spot actually better than the one 50 cm to the left?
>
> How it works: RoomScope writes a sine-sweep WAV. You play it through your
> monitors from any DAW and record your mic on another track, then export
> that track. RoomScope finds the sweep in the file (no trimming needed) and
> reports:
>
> - reverberation (EDT/T20/T30 → RT60) per octave band
> - early reflections, e.g. a desk bounce ~2 ms after the direct sound, with its level
> - frequency response, noise floor and mains hum
> - possible low-frequency room modes
>
> Then you compare two positions and see what changed: which reflections
> went away, whether the low end moved, whether the noise floor dropped.
>
> It is honest about bad data: if the decay is too noisy for a T30, it says
> "insufficient decay range" instead of printing a number. Levels are dBFS
> unless you calibrate. There is no magic room score.
>
> **Where it stands:** alpha. The analysis is tested with synthetic rooms,
> but I have not confirmed it on many real interfaces yet. That is where I
> would really appreciate help. If you have 15 minutes, an interface and a
> mic (a measurement mic is ideal, but anything omni is useful), the testing
> guide is in the repo. Failure reports are as welcome as successes.
>
> You can try it without any hardware (`roomscope demo` simulates a room).
> It is not meant to replace REW; it is a narrower tool focused on recording
> positions and on working through whatever DAW you already use.
>
> GitHub: https://github.com/jingyemingyue/RoomScope
>
> Happy to answer questions, and critical feedback on the measurement side
> is very welcome.

## 6. Reddit: r/opensource

**Title:** RoomScope: open-source room acoustics analysis for recording engineers (Python, Apache-2.0)

> RoomScope measures a recording room from a sine sweep played and recorded
> in any DAW, and reports reverberation time, early reflections, frequency
> response, noise floor and low-frequency resonances, with a comparison of
> two microphone positions.
>
> Some things that might interest this sub:
>
> - Apache-2.0, clean-room implementation of published methods (Farina's
>   sweep, Schroeder integration, Lundeby truncation, ISO 3382 definitions);
>   every dependency and its license is documented.
> - One analysis core shared by a CLI, a PySide6 desktop app (LGPL modules
>   only) and a Python API; results are JSON with published schemas.
> - Every metric carries a validity flag; the code prefers "can't tell" over
>   a plausible guess.
> - English and Simplified Chinese UI.
>
> It is alpha. The synthetic test suite passes on Linux, macOS and Windows;
> real-hardware testing is the current gap, so hardware reports are the most
> useful contribution. There are also good first issues around DAW-specific
> docs.
>
> https://github.com/jingyemingyue/RoomScope

## 7. Hacker News (Show HN)

**Title:** Show HN: RoomScope – measure a recording room through any DAW (open source)

> RoomScope is an open-source room acoustics analyzer for recording. It
> writes a sine-sweep WAV; you play and record it in whatever DAW you use;
> it deconvolves the recording into an impulse response and reports RT60 per
> octave band, early reflections, frequency response, noise floor and
> low-frequency resonances, and compares two microphone positions.
>
> Design choices: WAV in / WAV out, no DAW integration; every number has a
> validity flag, and it declines to report a metric the data cannot support
> (no "room score"); a CLI, a Qt app and a Python API share one pure
> NumPy/SciPy core. `roomscope demo` runs the whole thing on a simulated
> room.
>
> It is alpha: tested synthetically on three OSes, not yet confirmed on much
> real hardware. I'd love feedback from anyone who measures rooms, and
> reports from people with an audio interface.

## 8. 中文录音社区介绍

**标题：** 开源的录音房间声学分析工具 RoomScope：用你自己的 DAW 测量，对比话筒位置（征集测试者）

> 大家好，我在做一个开源项目 RoomScope，想解决录音时常遇到的问题：这个话筒位置到底好不好？
> 往左挪 50 cm 会不会更好？
>
> 使用方式：RoomScope 生成一个扫频 WAV，你在任何 DAW 里通过监听音箱播放，同时用话筒录下来，
> 再把录音导出成 WAV（不需要裁剪）。RoomScope 会自动找到扫频并给出：
>
> - 各倍频程的混响（EDT / T20 / T30 → RT60）
> - 早期反射，比如桌面在直达声后约 2 ms 的反射及其电平
> - 频率响应、本底噪声和电源哼声
> - 可能的低频房间共振
>
> 然后可以对比两个位置：哪些反射消失了，低频有没有变化，底噪有没有降低。
>
> 它会如实说明数据质量：衰减不够干净时会提示“衰减范围不足”，而不是硬给一个数字；
> 未校准时电平是 dBFS，不冒充 dB SPL；也没有所谓的“房间评分”。
>
> **目前状态：** Alpha 版。分析流程用合成房间测试过，但还没有在很多真实声卡上确认。
> 如果你有声卡和话筒（测量话筒最好，普通全指向话筒也有帮助），愿意花 15 分钟试一下，
> 仓库里有硬件测试指南，失败的反馈和成功的一样有价值。
>
> 不需要任何硬件也能先体验：`roomscope --lang zh_CN demo` 会模拟一个房间。
> 界面支持简体中文。它不是 REW 的替代品，而是一个更专注于录音摆位、配合现有 DAW 使用的小工具。
>
> GitHub：https://github.com/jingyemingyue/RoomScope
>
> 欢迎提问和批评，尤其是测量方法方面的意见。
