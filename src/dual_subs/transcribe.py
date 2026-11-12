"""Mandarin speech to timed Chinese lines with FireRedASR2S. Model choice: docs/adr/0001-speech-to-text.md."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

MODELS = Path(os.environ.get("DUAL_SUBS_MODELS", "D:/models/fireredasr2s"))
HF_REPOS = {
    "FireRedASR2-AED": "FireRedTeam/FireRedASR2-AED",
    "FireRedVAD": "FireRedTeam/FireRedVAD",
    "FireRedPunc": "FireRedTeam/FireRedPunc",
}
RATE = 16000
CJK = re.compile(r"[\u4e00-\u9fff]")


class Transcriber:
    def __init__(self) -> None:
        from huggingface_hub import snapshot_download

        for name, repo in HF_REPOS.items():
            if not (MODELS / name).is_dir():
                snapshot_download(repo, local_dir=MODELS / name)

        from fireredasr2s import FireRedAsr2System, FireRedAsr2SystemConfig
        from fireredasr2s.fireredasr2 import FireRedAsr2Config

        system = FireRedAsr2System(
            FireRedAsr2SystemConfig(
                vad_model_dir=str(MODELS / "FireRedVAD/VAD"),
                asr_model_dir=str(MODELS / "FireRedASR2-AED"),
                punc_model_dir=str(MODELS / "FireRedPunc"),
                # Word timestamps let punctuation split a speech stretch into sentences;
                # without them one line can run 15 s.
                asr_config=FireRedAsr2Config(return_timestamp=True),
                enable_lid=False,
            )
        )
        self.vad, self.asr, self.punc = system.vad, system.asr, system.punc

    def lines(self, mkv: Path, audio_index: int) -> list[dict]:
        """[{start, end, text}] in seconds for one audio stream of the file."""
        import soundfile

        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(mkv), "-map", f"0:{audio_index}"]
                + ["-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", str(wav)],
                check=True,
            )
            audio, _ = soundfile.read(wav, dtype="int16")
            stretches = self.vad.detect(str(wav))[0]["timestamps"]
        out = []
        for start, end in stretches:
            out += self._stretch(start, end, audio[int(start * RATE) : int(end * RATE)])
        return out

    def _stretch(self, start: float, end: float, samples) -> list[dict]:
        """Lines for one speech stretch; a stretch the timestamp steps choke on becomes one line."""
        uttid = f"s{int(start * 1000)}"
        try:
            result = self.asr.transcribe([uttid], [(RATE, samples)])[0]
        except RuntimeError:  # word alignment fails on long repetitive stretches, such as songs
            self.asr.config.return_timestamp = False
            try:
                result = self.asr.transcribe([uttid], [(RATE, samples)])[0]
            finally:
                self.asr.config.return_timestamp = True
        text = result.get("text", "").strip()
        if not CJK.search(text):
            return []  # English lyrics and noise; the English track covers lyrics
        if result.get("timestamp"):
            try:
                sentences = self.punc.process_with_timestamp([result["timestamp"]], [uttid])[0][
                    "punc_sentences"
                ]
            except AssertionError:  # its token matching breaks on mixed English and Chinese
                sentences = []
            if sentences:
                lines = [
                    {"start": start + s["start_s"], "end": start + s["end_s"], "text": s["punc_text"]}
                    for s in sentences
                ]
                lines[0]["start"], lines[-1]["end"] = start, end
                return lines
        return [{"start": start, "end": end, "text": self.punc.process([text], [uttid])[0]["punc_text"]}]
