from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from livekit import rtc

from app.integrations.faster_whisper import FasterWhisperSTT


def test_transcribe_drops_high_no_speech_segments():
    whisper = FasterWhisperSTT()
    whisper.__dict__["_model"] = MagicMock()
    whisper._model.transcribe.return_value = (
        iter(
            [
                SimpleNamespace(text=" Terima kasih.", no_speech_prob=0.9),
                SimpleNamespace(text=" Halo Andora.", no_speech_prob=0.1),
            ]
        ),
        MagicMock(),
    )

    text = whisper._transcribe(np.zeros(16000, dtype=np.float32), "id")

    assert text == "Halo Andora."


@pytest.mark.asyncio
async def test_recognize_downmixes_stereo_audio():
    stereo_samples = np.array([[32767, -32768], [16384, 16384]], dtype=np.int16)
    frame = rtc.AudioFrame(
        data=stereo_samples.tobytes(),
        sample_rate=16000,
        num_channels=2,
        samples_per_channel=2,
    )
    whisper = FasterWhisperSTT()

    with patch.object(whisper, "_transcribe", return_value="halo") as transcribe:
        await whisper.recognize(frame, language="id")

    audio, _ = transcribe.call_args.args
    assert len(audio) == 2
    assert abs(audio[0]) <= 1 / 32768.0
    assert audio[1] == pytest.approx(0.5, abs=1 / 32768.0)


@pytest.mark.asyncio
async def test_recognize_converts_pcm_and_returns_transcript():
    samples = np.zeros(1600, dtype=np.int16)
    frame = rtc.AudioFrame(
        data=samples.tobytes(),
        sample_rate=16000,
        num_channels=1,
        samples_per_channel=len(samples),
    )
    whisper = FasterWhisperSTT()

    with patch.object(whisper, "_transcribe", return_value="halo andora") as transcribe:
        event = await whisper.recognize(frame, language="id")

    audio, language = transcribe.call_args.args
    assert audio.dtype == np.float32
    assert language == "id"
    assert event.alternatives[0].text == "halo andora"
    assert event.alternatives[0].language == "id"
