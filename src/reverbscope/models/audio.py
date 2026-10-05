"""In-memory audio signal container."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from reverbscope.errors import InvalidAudioError
from reverbscope.i18n import _, diag

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class AudioSignal:
    """A mono or multi-channel signal in float64, shape ``(n,)`` or ``(n, channels)``."""

    samples: FloatArray
    sample_rate: int
    source: str | None = None
    #: Problems the audio device reported while recording this take (buffer
    #: under/overflows); :func:`reverbscope.core.pipeline.analyze` carries them
    #: into the result's warnings.
    device_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise InvalidAudioError(_("sample_rate must be positive"))
        if self.samples.ndim not in (1, 2):
            raise InvalidAudioError(_("samples must be 1-D (mono) or 2-D (frames, channels)"))
        if self.samples.shape[0] == 0:
            raise InvalidAudioError(_("signal is empty"))
        if not np.all(np.isfinite(self.samples)):
            raise InvalidAudioError(_("signal contains NaN or infinite samples"))

    @property
    def n_samples(self) -> int:
        return int(self.samples.shape[0])

    @property
    def n_channels(self) -> int:
        return 1 if self.samples.ndim == 1 else int(self.samples.shape[1])

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.sample_rate

    def channel(self, index: int) -> FloatArray:
        if index < 0 or index >= self.n_channels:
            raise InvalidAudioError(
                _("channel {index} does not exist (signal has {count} channel(s))").format(
                    index=index, count=self.n_channels
                )
            )
        if self.samples.ndim == 1:
            return self.samples
        return np.ascontiguousarray(self.samples[:, index])

    def select_channel(self, index: int | None) -> tuple[FloatArray, int, str | None]:
        """Return ``(mono, chosen_index, warning)``.

        ``index=None`` selects the channel with the highest RMS level, which is
        the usual case when a DAW exported a stereo file with the measurement
        microphone on one side.
        """
        if self.n_channels == 1:
            return self.channel(0), 0, None
        if index is not None:
            return self.channel(index), index, None
        rms = np.sqrt(np.mean(self.samples.astype(np.float64) ** 2, axis=0))
        chosen = int(np.argmax(rms))
        warning = diag(
            "recording has {count} channels; channel {chosen} (highest RMS) "
            "was analysed. Use the channel setting to choose explicitly.",
            count=self.n_channels,
            chosen=chosen,
        )
        return self.channel(chosen), chosen, warning
