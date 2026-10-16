"""Create a local hardware/DAW report; never run a take or award a hardware pass.

Standard library only: also works with --executable pointing to a downloaded
Desktop/Terminal executable, including the older roomscope executable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CHECKS = (
    ("first_launch", "Installed app first launch", "安装包首次启动"),
    ("enumeration", "Device enumeration", "设备枚举"),
    (
        "channels",
        "Input/output channel mapping (including >2 if available)",
        "输入输出通道映射（如有，含第 2 通道以外）",
    ),
    ("rate_44100", "Full take at 44.1 kHz", "44.1 kHz 完整播放与录音"),
    ("rate_48000", "Full take at 48 kHz", "48 kHz 完整播放与录音"),
    ("rate_96000", "Full take at 96 kHz", "96 kHz 完整播放与录音"),
    ("stop", "Stop during playback", "播放中停止"),
    ("disconnect", "Device unplug and recovery", "拔出设备与恢复"),
    ("latency", "Reported stream latency and buffer warnings", "流延迟报告与缓冲警告"),
    ("loopback", "Physical loopback capture", "物理回送录音"),
    ("save_reopen", "Save, quit, reopen and compare result", "保存、退出、重新打开并对照结果"),
    ("native_gui", "Native window, controls and language", "原生窗口、控件和语言"),
    (
        "daw_roundtrip",
        "DAW sweep / microphone recording / export / analysis",
        "DAW 扫频、话筒录音、导出与分析",
    ),
    ("daw_rate_negative", "DAW deliberate rate mismatch", "DAW 故意采样率不匹配"),
    ("daw_stretch_negative", "DAW deliberate time stretch", "DAW 故意时间伸缩"),
)

# Reports deliberately omit paths/settings and arbitrary exception strings.
# Device names remain useful for reproduction, but need human privacy review.
ENVIRONMENT_KEYS = (
    "reverbscope",
    "roomscope",  # public beta 1 predates the rename
    "edition",
    "frozen_bundle",
    "python",
    "implementation",
    "platform",
    "machine",
    "language",
    "packages",
    "libsndfile",
    "audio",
    "audio_callbacks",
)
PATH = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;|\"<>]*")


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[omitted; inspect locally]" if "error" in key.casefold() else _scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return PATH.sub("[redacted path]", value)
    return value


def collect_environment(executable: str, probe: bool) -> tuple[str, dict[str, Any]]:
    command = [executable, "doctor", "--json"]
    if probe:
        command.append("--probe")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", timeout=45
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return "FAIL", {
            "collection_error": "Executable unavailable or doctor timed out; inspect locally."
        }
    if result.returncode:
        return "FAIL", {"collection_error": f"doctor exited {result.returncode}; inspect locally."}
    try:
        raw = json.loads(result.stdout)
    except ValueError:
        return "FAIL", {"collection_error": "doctor did not return JSON; inspect locally."}
    if not isinstance(raw, dict) or not any(
        isinstance(raw.get(name), str) for name in ("reverbscope", "roomscope")
    ):
        return "FAIL", {
            "collection_error": "doctor JSON has no application version; inspect locally."
        }
    safe = {key: _scrub(raw[key]) for key in ENVIRONMENT_KEYS if key in raw}
    build = raw.get("build")
    if isinstance(build, dict) and re.fullmatch(r"[0-9a-fA-F]{7,40}", str(build.get("commit", ""))):
        safe["build_commit"] = build["commit"]
    return "Automated PASS", safe


def prepare(
    out: Path, executable: str, daw: str, language: str, probe: bool, collect: bool
) -> None:
    # Refuse a reused directory before invoking anything: never overwrite a
    # tester's filled-in report, log or private recording.
    out.mkdir(parents=True, exist_ok=False)
    status, environment = collect_environment(executable, probe) if collect else ("NOT RUN", {})
    zh = language == "zh-CN"
    metadata = {
        "created_utc": datetime.now(UTC).isoformat(),
        "daw": _scrub(daw),
        "language": language,
        "environment_collection": status,
        "sample_rates_probed": probe and collect and status == "Automated PASS",
        "checks": {key: "NOT RUN" for key, _en, _zh in CHECKS},
        "note": "Environment collection never certifies hardware or DAW compatibility.",
    }
    (out / "environment.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "run.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    intro = (
        "# 实机测试报告\n\n所有项目从 NOT RUN 开始。仅在真实设备上执行后手动填写 Hardware PASS 或 FAIL；跳过需说明原因。\n"
        "环境采集的 Automated PASS 只表示采集成功。发布前检查设备名、截图和附件中的私人信息。\n"
        "请填写：版本/构建 SHA、包 SHA256、日期、系统/CPU、接口/驱动、话筒/音箱、通道、采样率、缓冲、DAW 版本。\n"
        if zh
        else "# Hardware / DAW test report\n\nEvery check starts NOT RUN. Manually record Hardware PASS or FAIL only after a physical run; explain skipped checks.\n"
        "Automated PASS for environment collection means collection only. Review device names, screenshots and attachments before posting.\n"
        "Fill in: version/build SHA, asset SHA256, test date, OS/CPU, interface/driver, mic/speaker, channels, rate, buffer, DAW version.\n"
    )
    rows = "\n".join(
        f"| {zh_label if zh else en_label} | NOT RUN | |" for _key, en_label, zh_label in CHECKS
    )
    footer = (
        "\n\n附件：environment.json、包校验值、audio stream: 行、缓冲警告、DAW 导出/伸缩设置截图、结果截图。"
        "优先提供 --no-audio 会话包；未经检查不要上传录音或完整日志。"
        "\n维护者：复现 → 最小回归用例 → 修复 → 报告者复测 → 链接到硬件矩阵。\n"
        if zh
        else "\n\nAttach: environment.json, asset checksum, audio stream: line, buffer warnings, DAW export/stretch screenshots, result screenshot."
        " Prefer a --no-audio session bundle; review recordings and full logs before sharing."
        "\nMaintainer: reproduce → minimal regression → fix → reporter retest → linked hardware matrix row.\n"
    )
    table = (
        "\n| 检查 | 状态 | 证据 / 原因 |\n| --- | --- | --- |\n"
        if zh
        else "\n| Check | Status | Evidence / reason |\n| --- | --- | --- |\n"
    )
    (out / "report.md").write_text(intro + table + rows + footer, encoding="utf-8")
    (out / "commands.txt").write_text(
        "Replace APP with the tested executable (roomscope for public beta 1; reverbscope for renamed builds).\n"
        "Run from a terminal; no playback is invoked by these commands. Review every attachment.\n"
        "APP doctor --json\nAPP doctor --probe\nAPP devices\nAPP show <session>\n"
        "APP session bundle <session> --no-audio --out report.zip\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--executable",
        default="reverbscope",
        help="App executable; a path is accepted without a shell.",
    )
    parser.add_argument("--daw", default="NOT RUN", help="DAW and version; no DAW is controlled.")
    parser.add_argument("--language", choices=("en", "zh-CN"), default="en")
    parser.add_argument(
        "--probe", action="store_true", help="Ask doctor to probe rates; never plays audio."
    )
    parser.add_argument(
        "--skip-environment", action="store_true", help="Only create the blank report."
    )
    args = parser.parse_args()
    try:
        prepare(
            args.out,
            args.executable,
            args.daw,
            args.language,
            args.probe,
            not args.skip_environment,
        )
    except FileExistsError:
        parser.error(
            "Output directory already exists; choose a new run directory to preserve earlier evidence."
        )
    except OSError:
        parser.error("Could not write the report directory; check access and free space.")
    print("Report prepared. Hardware and DAW checks remain NOT RUN. Review locally before sharing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
