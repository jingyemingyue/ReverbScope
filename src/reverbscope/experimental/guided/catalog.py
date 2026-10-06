"""Offline knowledge catalog. English and Simplified Chinese are complete.

Other language codes are accepted. Until a community translation exists, the
full sentences stay in English and the report says so in that language.
Copy never contains a measured number. The report inserts evidence itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from reverbscope.experimental.guided.findings import FindingType

SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "en",
    "zh-CN",
    "zh-Hant",
    "ja",
    "ko",
    "es",
    "fr",
    "de",
    "pt",
)
COMPLETE_LANGUAGES = frozenset({"en", "zh-CN"})


@dataclass(frozen=True)
class FindingCopy:
    title: str
    what: str
    why: str
    impact: str
    causes: tuple[str, ...]
    action: str
    verify: str


@dataclass(frozen=True)
class ResolvedCopy:
    language: str
    requested: str
    complete: bool
    notice: str | None
    copy: FindingCopy


def normalize_language(language: str | None) -> str:
    if not language:
        return "en"
    raw = language.strip().replace("_", "-")
    lowered = raw.lower()
    aliases = {
        "en": "en",
        "en-us": "en",
        "en-gb": "en",
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-tw": "zh-Hant",
        "zh-hk": "zh-Hant",
        "zh-hant": "zh-Hant",
        "ja": "ja",
        "ja-jp": "ja",
        "ko": "ko",
        "ko-kr": "ko",
        "es": "es",
        "fr": "fr",
        "de": "de",
        "pt": "pt",
        "pt-br": "pt",
    }
    return aliases.get(lowered, "en")


_PARTIAL_NOTICE = {
    "zh-Hant": "完整離線說明目前只有英文與簡體中文。以下為英文。",
    "ja": "オフラインの全文は、英語と簡体字中国語だけです。以下は英語です。",
    "ko": "오프라인 전문은 영어와 간체 중국어만 있습니다. 아래는 영어입니다.",
    "es": "El texto completo sin conexión está en inglés.",
    "fr": "Le texte hors ligne complet est en anglais.",
    "de": "Der vollständige Offline-Text ist auf Englisch.",
    "pt": "O texto completo offline está em inglês.",
}


def _c(
    title: str,
    what: str,
    why: str,
    impact: str,
    causes: tuple[str, ...],
    action: str,
    verify: str,
) -> FindingCopy:
    return FindingCopy(title, what, why, impact, causes, action, verify)


_EN: dict[FindingType, FindingCopy] = {
    FindingType.STRONG_EARLY_REFLECTION: _c(
        "A strong early reflection",
        "A reflection arrives soon after the direct sound and is loud next to it.",
        "Early energy this strong can comb-filter the source.",
        "A voice or close instrument can sound boxy, hollow, or phasey even when the later decay is fine.",
        (
            "It may come from a nearby desk, wall, ceiling, floor, or another hard surface.",
            "The measurement does not identify which surface.",
        ),
        "Move the microphone or the source a short distance, or temporarily cover the nearest hard surface with something soft.",
        "Measure again. The early reflection should be weaker or later. If it is not, try a different surface and measure again.",
    ),
    FindingType.LOW_FREQUENCY_DECAY_LONG: _c(
        "Low frequencies decay longer than the mids",
        "The low-frequency decay is clearly longer than the mid-frequency decay.",
        "The low end is ringing after the rest of the sound has died.",
        "Bass can sound muddy or keep ringing under a voice, guitar, or mix.",
        (
            "A small room often does this at its low modes.",
            "A nearby boundary can add to it. The measurement does not name the boundary.",
        ),
        "Move the microphone, and if you can the source, away from the nearest wall or corner. Do not buy treatment yet.",
        "Measure again and compare the low decay with the mid decay. Keep the move only if the low end shortens without a new problem.",
    ),
    FindingType.LOW_FREQUENCY_PEAK: _c(
        "A low-frequency peak",
        "One low frequency stands out of the response around it.",
        "That frequency is louder than its neighbours.",
        "A note in that range can boom or jump out of a take.",
        (
            "It may be a room mode, a loudspeaker effect, or a boundary.",
            "The measurement does not say which.",
        ),
        "Move the microphone a short distance and measure again before changing the room.",
        "Compare the same frequency. Keep the move only if that peak gets smaller and nothing important gets worse.",
    ),
    FindingType.LOW_FREQUENCY_NULL: _c(
        "A low-frequency dip",
        "One low frequency is weaker than the response around it.",
        "Energy at that frequency is cancelling or falling into a dip.",
        "A note in that range can disappear or sound thin.",
        (
            "It may be boundary interference, the loudspeaker, or the microphone position.",
            "The measurement does not say which.",
        ),
        "Move the microphone a short distance and measure again. Do not equalise the dip until the move has been checked.",
        "Compare the same frequency. The dip should get shallower. If it follows the loudspeaker, the room move will not fix it.",
    ),
    FindingType.HIGH_NOISE_FLOOR: _c(
        "A high noise floor",
        "The quiet part of the recording is louder than it should be for a home take.",
        "Noise fills the gaps and can hide or bias the decay.",
        "A quiet voice or a soft instrument will sit closer to the hiss, hum, or room noise.",
        (
            "It may be the room, a computer fan, a preamp, or too much gain.",
            "Levels are uncalibrated, so this is not a sound-pressure reading.",
        ),
        "Turn off nearby noise, lower unnecessary gain, and take one more measurement in the quieter setup.",
        "The quiet-part level should drop. If the decay numbers also change, trust the quieter take.",
    ),
    FindingType.MAINS_HUM_DETECTED: _c(
        "Mains hum",
        "A mains tone and its harmonics stand out of the noise.",
        "Hum is a steady tone, not room decay.",
        "It can ride under a take and is hard to remove afterwards without touching the music.",
        (
            "It may come from grounding, cables, dimmers, or a power supply.",
            "The measurement does not say which device.",
        ),
        "Move the cable run, try another outlet or a shorter cable, and measure again. Do not lift a safety ground.",
        "The hum tone should drop. If it does not, change one more thing and measure again.",
    ),
    FindingType.INSUFFICIENT_DECAY_RANGE: _c(
        "Not enough decay range",
        "The decay does not fall far enough above the noise to support every reverberation number.",
        "A reverberation time needs a clean drop. This take does not have one for the metric that was withheld.",
        "A number invented for the missing metric would not be a measurement.",
        (
            "The noise floor may be high, the sweep short, or the playback level low.",
            "That is a limit of this take, not a room score.",
        ),
        "Use a longer sweep, a little more playback level if it is not already hot, or a quieter room, then measure again.",
        "The withheld metric should then be reported. Until then, do not quote it.",
    ),
    FindingType.LOW_DIRECT_SOUND_CONFIDENCE: _c(
        "The direct sound is uncertain",
        "The direct sound could not be identified with confidence.",
        "Delays and reflection levels are measured from that instant.",
        "Reflection times and any placement reading may be off until this is fixed.",
        (
            "The reference sweep may be the wrong file, or the loudspeaker may have distorted.",
            "The measurement does not choose between those.",
        ),
        "Check that the reference sweep matches the one that was played, lower the level if the loudspeaker distorts, and measure again.",
        "The direct-sound confidence should be high on the next take before you act on reflection times.",
    ),
    FindingType.INPUT_TOO_HOT: _c(
        "The input is close to clipping",
        "The recording peak sits close to the top of the file, but a flat-topped clip was not found.",
        "A small extra gain will clip and make the decay unusable.",
        "The take may be fine now and fail the next time the level creeps up.",
        ("Playback level or input gain may be high.",),
        "Lower the playback or the input a little and measure again.",
        "The peak should sit lower, and the clip check should stay clear.",
    ),
    FindingType.SIGNAL_TOO_LOW: _c(
        "The signal is very low",
        "The recording is far below full scale, or the quiet part is digital silence.",
        "A microphone recording is never exact silence. A very quiet file leaves the decay in the noise.",
        "Room numbers from this take are easy to misread.",
        (
            "The microphone track may not have been the one exported.",
            "A gate, noise reduction, or a low gain can do this too.",
        ),
        "Export the microphone track with processing off, raise the gain if the file is simply quiet, and measure again.",
        "You should hear a real noise floor, and the peak should no longer be buried.",
    ),
    FindingType.CLIPPING_DETECTED: _c(
        "The recording clips",
        "The file has flat-topped peaks.",
        "Clipped peaks are not the room. They bend every level and can fake a decay.",
        "Do not trust this take for room decisions.",
        ("Playback level or input gain is high enough to flatten the wave.",),
        "Lower the playback or the input and measure again. Do not use this take.",
        "The next take should show no flat-topped peaks.",
    ),
    FindingType.SAMPLE_RATE_MISMATCH: _c(
        "The sweep was played at the wrong sample rate",
        "The sweep in the recording does not run at the speed it was generated at.",
        "Every time and frequency is scaled by that speed error.",
        "Room numbers from this take are not the room.",
        (
            "The project rate and the sweep file rate differ, and the file was not converted on import.",
        ),
        "Generate the sweep at the project rate, or let the project convert it on import, and measure again.",
        "The next take should not report a sample-rate mismatch.",
    ),
    FindingType.TIME_STRETCH_DETECTED: _c(
        "The sweep was time-stretched",
        "The sweep in the recording does not run at the speed it was generated at.",
        "A stretch changes every time and frequency.",
        "Room numbers from this take are not the room.",
        (
            "A stretch mode may be on for the sweep clip.",
            "The measurement does not name the product setting.",
        ),
        "Turn time-stretch off for the sweep clip and measure again.",
        "The next take should not report a stretch.",
    ),
    FindingType.DEVICE_TIMING_SUSPICIOUS: _c(
        "The devices may not share one clock",
        "Playback and recording did not clearly share one clock.",
        "Two clocks drift. The impulse response smears.",
        "Decay and reflection times can look worse than the room.",
        ("Separate devices without a shared clock can do this.",),
        "Record and play on one device, or clock them together, and measure again.",
        "The timing warning should be gone on the next take.",
    ),
    FindingType.AUDIO_DROPOUT_DETECTED: _c(
        "The audio device dropped buffers",
        "The device reported dropped or late buffers during the take.",
        "Missing samples smear the impulse response.",
        "This take can look more reverberant, or simply wrong, because of the device rather than the room.",
        ("The buffer may be too small, or the computer was busy.",),
        "Close other audio programs, raise the buffer size, and measure again.",
        "The next take should not report a dropped buffer.",
    ),
}

_ZH: dict[FindingType, FindingCopy] = {
    FindingType.STRONG_EARLY_REFLECTION: _c(
        "较强的早期反射",
        "直达声之后很快又来了一声，而且它相对直达声并不弱。",
        "这么强的早期反射会让直达声和反射声叠在一起，形成梳状染色。",
        "人声或近距离乐器可能发闷、发空，或带着相位感，即使后面的混响并不长。",
        (
            "可能来自附近的桌面、墙面、天花板、地面或其他硬表面。",
            "这次测量不能确定是哪一个表面。",
        ),
        "先把话筒或声源挪开一小段，或临时在最近的硬表面上垫一层软的东西。先不要购买材料。",
        "再测一次。这声早期反射应当变弱或变晚。如果没有变，换一个表面再测。",
    ),
    FindingType.LOW_FREQUENCY_DECAY_LONG: _c(
        "低频衰减比中频更长",
        "低频段的衰减明显长于中频。",
        "其余声音已经落下时，低频还在响。",
        "低音可能发浑，或在人声、吉他和混音下面拖着不走。",
        (
            "小房间的低频模式经常如此。",
            "靠近某个边界也可能加重。测量不能指出是哪一个边界。",
        ),
        "先把话筒，以及可能的话把声源，从最近的墙或墙角移开。先不要购买低频处理。",
        "再测一次，把低频衰减和中频放在一起看。只有低频变短、而且没有新问题时才保留这次挪动。",
    ),
    FindingType.LOW_FREQUENCY_PEAK: _c(
        "一个低频峰",
        "某个低频比它周围更突出。",
        "这个频率比邻近频率更响。",
        "落在这个范围的音可能突然变轰，或从录音里跳出来。",
        (
            "可能是房间模式、扬声器特性，或某个边界。",
            "测量不能确定是哪一个。",
        ),
        "先把话筒挪开一小段再测，先不要改房间。",
        "对比同一个频率。只有这个峰变小、而且没有更重要的问题变坏时，才保留这次挪动。",
    ),
    FindingType.LOW_FREQUENCY_NULL: _c(
        "一个低频凹陷",
        "某个低频比它周围更弱。",
        "这个频率上的能量在抵消，或落进一个凹陷。",
        "落在这个范围的音可能变轻或变薄。",
        (
            "可能是边界干涉、扬声器，或话筒位置。",
            "测量不能确定是哪一个。",
        ),
        "先把话筒挪开一小段再测。在这次挪动被验证之前，不要先用均衡去填这个凹陷。",
        "对比同一个频率。凹陷应当变浅。如果它跟着扬声器走，挪房间解决不了。",
    ),
    FindingType.HIGH_NOISE_FLOOR: _c(
        "噪声底偏高",
        "录音里安静的那一段，对家庭录音来说偏响。",
        "噪声会填满空隙，也可能影响衰减的判断。",
        "轻声或小声乐器会离嘶声、哼声或房间噪声更近。",
        (
            "可能是房间、电脑风扇、前置放大器，或增益过高。",
            "这里没有校准成声压级，所以不是分贝声压读数。",
        ),
        "先关掉附近的噪声，把不必要的增益降下来，再用更安静的设置测一次。",
        "安静段的电平应当下降。如果衰减数字也变了，以更安静的那一次为准。",
    ),
    FindingType.MAINS_HUM_DETECTED: _c(
        "检测到电源哼声",
        "噪声里有一条电源基频和它的谐波。",
        "这是持续的音调，不是房间衰减。",
        "它会垫在录音下面，事后很难去掉而不碰到音乐。",
        (
            "可能来自接地、线缆、调光器或电源。",
            "测量不能指出是哪一台设备。",
        ),
        "整理线缆路径，换一个插座或更短的线，再测一次。不要拆掉安全地线。",
        "这条哼声应当下降。如果没有，只再改一件事，然后重测。",
    ),
    FindingType.INSUFFICIENT_DECAY_RANGE: _c(
        "衰减范围不够",
        "衰减没有在噪声之上落下足够的范围，因此不是每一个混响数字都能给出。",
        "混响时间需要一段干净的下落。被标成无效的那一项，这次没有。",
        "给无效指标补一个数字，并不是测量。",
        (
            "可能是噪声底偏高、扫频偏短，或播放电平偏低。",
            "这是这一次测量的限制，不是房间评分。",
        ),
        "用更长的扫频；如果电平还没有顶满，可以略微提高播放电平；或在更安静的时候再测。",
        "被扣下的那一项应当变成有效。在那之前不要引用它。",
    ),
    FindingType.LOW_DIRECT_SOUND_CONFIDENCE: _c(
        "直达声不够确定",
        "直达声没有被有把握地认出来。",
        "延迟和反射电平都从这个时刻算起。",
        "在修好之前，反射时间和摆位读数都可能偏。",
        (
            "参考扫频可能不是播放的那一个文件，或扬声器已经失真。",
            "测量不会替你选定原因。",
        ),
        "确认参考扫频就是播放的那一个；如果扬声器失真，先降低电平，再测一次。",
        "下一次的直达声把握应当是高。在那之前，不要根据反射时间做决定。",
    ),
    FindingType.INPUT_TOO_HOT: _c(
        "输入接近削波",
        "录音峰值已经靠近文件的顶端，但还没有检出平顶削波。",
        "再大一点就会削波，衰减就不可用了。",
        "这一次也许还能用，电平再往上就会失败。",
        ("播放电平或输入增益可能偏高。",),
        "把播放或输入稍微降一点，再测一次。",
        "峰值应当更低，削波检查应当仍然干净。",
    ),
    FindingType.SIGNAL_TOO_LOW: _c(
        "信号过小",
        "整段录音离满刻度很远，或安静的部分是数字静音。",
        "话筒录音不会是精确的静音。太小的文件会让衰减落在噪声里。",
        "这一次的房间数字很容易读错。",
        (
            "导出的可能不是话筒轨。",
            "噪声门、降噪，或增益过低也会这样。",
        ),
        "关掉处理，导出话筒轨；如果只是增益低，再把增益抬起来，然后重测。",
        "应当能听到真实的噪声底，峰值也不再埋得很深。",
    ),
    FindingType.CLIPPING_DETECTED: _c(
        "录音发生了削波",
        "文件里有被削平的峰值。",
        "削平的峰不是房间。它会扭电平，也可能假造一段衰减。",
        "不要用这一次做房间上的决定。",
        ("播放电平或输入增益已经高到把波形削平。",),
        "降低播放或输入，重新测量。不要使用这一次。",
        "下一次不应当再出现平顶峰值。",
    ),
    FindingType.SAMPLE_RATE_MISMATCH: _c(
        "扫频以错误的采样率播放",
        "录音里的扫频速度和生成时不一致。",
        "所有时间和频率都会按这个速度误差缩放。",
        "这一次的房间数字不是房间本身。",
        ("工程采样率和扫频文件不一致，而且导入时没有做转换。",),
        "按工程采样率重新生成扫频，或在导入时让工程转换它，然后重测。",
        "下一次不应当再报告采样率不一致。",
    ),
    FindingType.TIME_STRETCH_DETECTED: _c(
        "扫频被时间拉伸",
        "录音里的扫频速度和生成时不一致。",
        "拉伸会改变所有时间和频率。",
        "这一次的房间数字不是房间本身。",
        (
            "扫频片段上可能开着拉伸。",
            "测量不会指出是哪一个软件开关。",
        ),
        "关掉扫频片段上的时间拉伸，然后重测。",
        "下一次不应当再报告拉伸。",
    ),
    FindingType.DEVICE_TIMING_SUSPICIOUS: _c(
        "设备时钟可能不一致",
        "播放和录音没有明确共用同一个时钟。",
        "两个时钟会漂移，脉冲响应会被抹开。",
        "衰减和反射时间可能看起来比房间本身更差。",
        ("没有共用时钟的两台设备会出现这种情况。",),
        "用同一台设备播放和录音，或让它们共用时钟，然后重测。",
        "下一次不应当再出现时钟警告。",
    ),
    FindingType.AUDIO_DROPOUT_DETECTED: _c(
        "音频设备丢了缓冲",
        "录音过程中设备报告了丢弃或过晚的缓冲。",
        "丢掉的采样会抹开脉冲响应。",
        "这一次看起来更混响，或干脆是错的，原因可能是设备而不是房间。",
        ("缓冲可能太小，或电脑当时很忙。",),
        "关掉其他音频程序，加大缓冲，然后重测。",
        "下一次不应当再报告缓冲问题。",
    ),
}


def resolve_copy(kind: FindingType, language: str | None) -> ResolvedCopy:
    requested = normalize_language(language)
    if requested == "zh-CN":
        return ResolvedCopy("zh-CN", requested, True, None, _ZH[kind])
    if requested == "en":
        return ResolvedCopy("en", requested, True, None, _EN[kind])
    notice = _PARTIAL_NOTICE.get(requested)
    return ResolvedCopy("en", requested, False, notice, _EN[kind])


_UI = {
    "en": {
        "badge": "Experimental",
        "title": "Guided check",
        "next": "The most important issue",
        "what": "What happened",
        "why": "Why this is a problem",
        "impact": "What it can do to a recording",
        "causes": "Possible causes",
        "action": "Try this first",
        "verify": "How to tell if it helped",
        "evidence": "Technical evidence",
        "source": "Source",
        "builtin": "Built-in explanation",
        "local": "Local model",
        "cloud": "Cloud model",
        "none": "No guided issue on this take.",
        "compare": "After the change",
        "improved": "Improved",
        "slightly_improved": "Slightly improved",
        "worse": "Worse",
        "slightly_worse": "Slightly worse",
        "unchanged": "Unchanged",
        "mixed": "Mixed",
        "not_comparable": "Not comparable",
        "new_issue": "New issue",
        "resolved": "No longer reported",
        "fallback": "Cloud explanation unavailable. Showing the built-in offline explanation instead.",
        "privacy_cloud": "Privacy mode is on, so the cloud model was not called.",
        "consent": "Cloud analysis needs an explicit send. Showing the built-in explanation.",
        "no_score": "There is no single room score.",
        "cost": "Requests made with your API key may incur charges from your AI provider.",
        "endpoint_warning": (
            "A custom endpoint may receive the data you choose to send. "
            "ReverbScope cannot guarantee the privacy practices of third-party servers."
        ),
        "observed": "Observed",
        "possible": "Possible",
        "recommendation": "Recommendation",
        "open_settings": "Guided assistant",
        "settings_title": "Guided assistant",
        "settings_hint": "Experimental. Built-in offline explanations are the default.",
        "engine": "Explanation",
        "engine_builtin": "Built-in offline explanations",
        "engine_local": "Local model",
        "engine_cloud": "Cloud model with my own key",
        "engine_auto": "Automatic: local model if installed, otherwise cloud only after you allow it",
        "provider": "Provider",
        "provider_openai": "OpenAI",
        "provider_anthropic": "Anthropic",
        "provider_gemini": "Google Gemini",
        "provider_openai_compatible": "OpenAI-compatible",
        "model": "Model",
        "model_hint": "Type the model id yourself. No name is assumed to be the best.",
        "key": "API key",
        "key_hint": "Hidden by default. Never written to settings, sessions, or logs.",
        "replace": "Replace",
        "remove": "Remove",
        "test_connection": "Test connection",
        "reveal_confirm": "I confirm that I want to see the full key",
        "reveal": "Show",
        "hide": "Hide",
        "base_url": "Custom address",
        "ack_endpoint": "I understand a custom server may receive the data I choose to send",
        "cloud_enabled": "Allow this provider to receive sanitized diagnostic context",
        "data_level": "Data sent",
        "level_minimal": "Minimal",
        "level_detailed": "Detailed",
        "length": "Explanation length",
        "length_concise": "Concise",
        "length_balanced": "Balanced",
        "length_detailed_choice": "Detailed",
        "expertise": "How much to show",
        "expertise_beginner": "Beginner, one next step",
        "expertise_intermediate": "Intermediate",
        "expertise_expert": "Expert",
        "consent_label": "Sending",
        "consent_unset": "Not allowed yet",
        "consent_once": "Allow once",
        "consent_always": "Always allow sanitized summaries",
        "privacy": "Privacy mode",
        "offline": "Offline mode",
        "lookup": "Allow public technical lookup",
        "share_usage": "Anonymous usage statistics",
        "share_hardware": "Hardware compatibility results",
        "share_crash": "Anonymous crash reports",
        "preview": "Preview data sent to the provider",
        "save": "Save",
        "cancel": "Cancel",
        "key_empty": "No new key was entered.",
        "key_not_stored": "The key was not stored.",
        "key_stored_secure": "The key was stored in the system credential store.",
        "key_stored_session": "The key is kept for this session only.",
        "key_removed": "The key was removed.",
        "configured": "A key is configured",
        "not_configured": "No key configured",
        "test_ok": "Connection succeeded. No measurement was sent.",
        "test_failed": "Connection failed. The measurement is unchanged.",
        "secure_unavailable": (
            "Secure credential storage is unavailable. "
            "Use the key for this session only, or cancel. It will not be written to a file."
        ),
        "secure_choice": "Store securely if possible",
        "session_choice": "Use for this session only",
        "cancel_choice": "Cancel",
        "local_status": (
            "An optional on-device model can be installed. "
            "It stays off until you install it, and it is never downloaded."
        ),
        "install_local": "Install the on-device model",
        "local_installed": "On-device model installed. You can switch back to the built-in explanation.",
        "local_install_failed": "The on-device model was not installed.",
        "packs_status": "Knowledge packs are optional. None are bundled or downloaded automatically.",
        "key_missing": "No API key is configured. Showing the built-in offline explanation instead.",
        "store_title": "Where should the key be kept?",
        "language_follow": "Follow the app",
        "language_en": "English",
        "language_zh": "Simplified Chinese",
        "language_label": "Explanation language",
    },
    "zh-CN": {
        "badge": "实验功能",
        "title": "导引检查",
        "next": "当前最重要的问题",
        "what": "发生了什么",
        "why": "为什么这是问题",
        "impact": "对录音可能有什么影响",
        "causes": "可能原因",
        "action": "先试这个",
        "verify": "如何确认有没有变好",
        "evidence": "技术证据",
        "source": "说明来源",
        "builtin": "内置说明",
        "local": "本地模型",
        "cloud": "云端说明",
        "none": "这一次没有需要导引的问题。",
        "compare": "改完之后",
        "improved": "有改善",
        "slightly_improved": "略有改善",
        "worse": "变差",
        "slightly_worse": "略差",
        "unchanged": "没有明显变化",
        "mixed": "有好有坏",
        "not_comparable": "不能对比",
        "new_issue": "新出现的问题",
        "resolved": "不再出现",
        "fallback": "云端说明不可用。以下改为内置离线说明。",
        "privacy_cloud": "隐私模式已打开，因此没有调用云端模型。",
        "consent": "云端分析需要单独确认发送。当前显示内置说明。",
        "no_score": "这里没有房间总分。",
        "cost": "使用你自己的密钥发出的请求，可能由服务商向你收费。",
        "endpoint_warning": "自定义服务器会收到你选择发送的数据。本程序不能保证第三方服务器如何处理这些数据。",
        "observed": "已观察到",
        "possible": "可能",
        "recommendation": "建议",
        "open_settings": "智能诊断助手",
        "settings_title": "智能诊断助手",
        "settings_hint": "实验功能。默认使用内置离线说明。",
        "engine": "说明方式",
        "engine_builtin": "内置离线说明",
        "engine_local": "本地模型",
        "engine_cloud": "自带密钥的云端说明",
        "engine_auto": "自动。已安装本地模型时用本地，否则只在你允许后使用云端。",
        "provider": "服务",
        "provider_openai": "常见云端服务",
        "provider_anthropic": "另一云端服务",
        "provider_gemini": "谷歌云端服务",
        "provider_openai_compatible": "自定义兼容服务",
        "model": "模型标识",
        "model_hint": "请自己填写。程序不会把某个名称当成永远最好的模型。",
        "key": "密钥",
        "key_hint": "默认隐藏。不会写入设置、会话或日志。",
        "replace": "替换",
        "remove": "移除",
        "test_connection": "测试连接",
        "reveal_confirm": "我确认要查看完整密钥",
        "reveal": "查看",
        "hide": "隐藏",
        "base_url": "自定义地址",
        "ack_endpoint": "我了解自定义服务器会收到我选择发送的数据",
        "cloud_enabled": "允许该服务接收已清理的诊断摘要",
        "data_level": "发送范围",
        "level_minimal": "最少",
        "level_detailed": "详细",
        "length": "说明长度",
        "length_concise": "简短",
        "length_balanced": "适中",
        "length_detailed_choice": "详细",
        "expertise": "详细程度",
        "expertise_beginner": "入门，一次只看下一步",
        "expertise_intermediate": "进阶",
        "expertise_expert": "专业",
        "consent_label": "发送许可",
        "consent_unset": "尚未允许发送",
        "consent_once": "只允许一次",
        "consent_always": "始终允许已清理的摘要",
        "privacy": "隐私模式",
        "offline": "离线模式",
        "lookup": "允许查询公开技术资料",
        "share_usage": "匿名使用统计",
        "share_hardware": "硬件兼容结果",
        "share_crash": "匿名崩溃报告",
        "preview": "预览将发送的内容",
        "save": "保存",
        "cancel": "取消",
        "key_empty": "还没有输入新密钥。",
        "key_not_stored": "没有保存密钥。",
        "key_stored_secure": "密钥已放入系统凭据库。",
        "key_stored_session": "密钥只保存在本次运行中。",
        "key_removed": "密钥已移除。",
        "configured": "已配置密钥",
        "not_configured": "尚未配置密钥",
        "test_ok": "连接成功。没有发送测量。",
        "test_failed": "连接没有成功。测量不受影响。",
        "secure_unavailable": "系统凭据库不可用。可以只在本次运行中使用，或取消。不会写入文件。",
        "secure_choice": "尽量放入系统凭据库",
        "session_choice": "仅本次运行",
        "cancel_choice": "取消",
        "local_status": "可以安装本机说明模型。安装之前不会启用，也不会自动下载。",
        "install_local": "安装本机说明模型",
        "local_installed": "本机说明模型已安装。可以改回内置说明。",
        "local_install_failed": "本机说明模型没有安装成功。",
        "packs_status": "知识包需要另行获取。当前没有附带，也不会自动下载。",
        "key_missing": "还没有配置密钥。以下改为内置离线说明。",
        "store_title": "密钥要放在哪里？",
        "language_follow": "跟随程序",
        "language_en": "英文",
        "language_zh": "简体中文",
        "language_label": "说明语言",
    },
}

_EVIDENCE_LABELS = {
    "en": {
        "delay_ms": "Delay",
        "relative_level_db": "Level relative to the direct sound",
        "count_in_window": "Arrivals in the window",
        "low_max_rt60_s": "Longest low-frequency decay",
        "mid_mean_rt60_s": "Average mid-frequency decay",
        "frequency_hz": "Frequency",
        "prominence_db": "Height above the surrounding lows",
        "depth_db": "Depth below the surrounding lows",
        "rms_dbfs": "Quiet-part level",
        "base_hz": "Hum fundamental",
        "peak_dbfs": "Recording peak",
        "generated_rate_hz": "Sweep file rate",
        "played_rate_hz": "Playback rate",
        "direct_sound_confidence": "Direct-sound confidence",
    },
    "zh-CN": {
        "delay_ms": "延迟",
        "relative_level_db": "相对直达声的电平",
        "count_in_window": "窗口内的到达次数",
        "low_max_rt60_s": "最长的低频衰减",
        "mid_mean_rt60_s": "中频衰减的平均",
        "frequency_hz": "频率",
        "prominence_db": "高出周围低频",
        "depth_db": "低于周围低频",
        "rms_dbfs": "安静段电平",
        "base_hz": "哼声基频",
        "peak_dbfs": "录音峰值",
        "generated_rate_hz": "扫频文件采样率",
        "played_rate_hz": "播放采样率",
        "direct_sound_confidence": "直达声把握",
    },
}


def ui_text(language: str | None, key: str) -> str:
    requested = normalize_language(language)
    table = _UI["zh-CN"] if requested == "zh-CN" else _UI["en"]
    return table[key]


def evidence_label(language: str | None, key: str) -> str:
    requested = normalize_language(language)
    table = _EVIDENCE_LABELS["zh-CN"] if requested == "zh-CN" else _EVIDENCE_LABELS["en"]
    return table.get(key, key)
