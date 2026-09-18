import asyncio
from functools import cached_property

import numpy as np
from faster_whisper import WhisperModel
from livekit import rtc
from livekit.agents import APIConnectOptions, stt, utils
from livekit.agents.types import NotGivenOr


class FasterWhisperSTT(stt.STT):
    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "id",
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=False,
                interim_results=False,
                offline_recognize=True,
            )
        )
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._language = language

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def provider(self) -> str:
        return "faster-whisper"

    @cached_property
    def _model(self) -> WhisperModel:
        return WhisperModel(
            self._model_name,
            device=self._device,
            compute_type=self._compute_type,
        )

    def _transcribe(self, audio: np.ndarray, language: str) -> str:
        segments, _ = self._model.transcribe(
            audio,
            language=language,
            task="transcribe",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(
            segment.text.strip()
            for segment in segments
            if segment.no_speech_prob < 0.6
        ).strip()

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: NotGivenOr[str],
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        frame = utils.merge_frames(buffer)
        if frame.num_channels > 1:
            samples = np.frombuffer(frame.data, dtype=np.int16).reshape(
                -1, frame.num_channels
            )
            mono = np.mean(samples.astype(np.float32), axis=1).astype(np.int16)
            frame = rtc.AudioFrame(
                data=mono.tobytes(),
                sample_rate=frame.sample_rate,
                num_channels=1,
                samples_per_channel=len(mono),
            )
        resampler = rtc.AudioResampler(
            input_rate=frame.sample_rate,
            output_rate=16000,
            num_channels=1,
        )
        frames = [*resampler.push(frame), *resampler.flush()]
        selected_language = language if isinstance(language, str) else self._language
        if not frames:
            text = ""
        else:
            merged = utils.merge_frames(frames)
            pcm = np.frombuffer(merged.data, dtype=np.int16)
            audio = pcm.astype(np.float32) / 32768.0
            text = await asyncio.to_thread(self._transcribe, audio, selected_language)

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt.SpeechData(
                    language=selected_language,
                    text=text,
                )
            ],
        )
