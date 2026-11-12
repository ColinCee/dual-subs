"""Mandarin speech to timed Chinese lines with FireRedASR2S. Model choice: docs/adr/0001-speech-to-text.md."""

import os
import subprocess
import tempfile
from pathlib import Path

MODELS = Path(os.environ.get("DUAL_SUBS_MODELS", "D:/models/fireredasr2s"))
HF_REPOS = {
    "FireRedASR2-AED": "FireRedTeam/FireRedASR2-AED",
    "FireRedVAD": "FireRedTeam/FireRedVAD",
    "FireRedPunc": "FireRedTeam/FireRedPunc",
}


class Transcriber:
    def __init__(self) -> None:
        from huggingface_hub import snapshot_download

        for name, repo in HF_REPOS.items():
            if not (MODELS / name).is_dir():
                snapshot_download(repo, local_dir=MODELS / name)

        from fireredasr2s import FireRedAsr2System, FireRedAsr2SystemConfig
        from fireredasr2s.fireredasr2 import FireRedAsr2Config

        cfg = FireRedAsr2SystemConfig(
            vad_model_dir=str(MODELS / "FireRedVAD/VAD"),
            asr_model_dir=str(MODELS / "FireRedASR2-AED"),
            punc_model_dir=str(MODELS / "FireRedPunc"),
            # With timestamps the system splits each speech stretch into sentences;
            # without them one line can run 15 s.
            asr_config=FireRedAsr2Config(return_timestamp=True),
            enable_lid=False,
        )
        self.system = FireRedAsr2System(cfg)

    def lines(self, mkv: Path, audio_index: int) -> list[dict]:
        """[{start, end, text}] in seconds for one audio stream of the file."""
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(mkv),
                    "-map",
                    f"0:{audio_index}",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(wav),
                ],
                check=True,
            )
            result = self.system.process(str(wav))
        return [
            {"start": s["start_ms"] / 1000, "end": s["end_ms"] / 1000, "text": s["text"]}
            for s in result["sentences"]
        ]
