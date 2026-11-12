"""Read MKV streams with ffprobe and write the dual track into a copy with ffmpeg."""

import json
import subprocess
from pathlib import Path

CHINESE = {"chi", "zho", "cmn"}
DUAL_TITLE = "中文 + English"


def streams(mkv: Path) -> list[dict]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(mkv)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    return json.loads(out)["streams"]


def duration(mkv: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mkv)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return float(out)


def _lang(s: dict) -> str:
    return s.get("tags", {}).get("language", "")


def _title(s: dict) -> str:
    return s.get("tags", {}).get("title", "")


def of_type(all_streams: list[dict], kind: str) -> list[dict]:
    return [s for s in all_streams if s["codec_type"] == kind]


def mandarin_audio(all_streams: list[dict]) -> dict | None:
    return next((s for s in of_type(all_streams, "audio") if _lang(s) in CHINESE), None)


def english_dialogue(all_streams: list[dict]) -> dict | None:
    """The full English track: not forced (signs only), not CC; the default one when there are several."""
    subs = [
        s
        for s in of_type(all_streams, "subtitle")
        if _lang(s) == "eng"
        and not s["disposition"].get("forced")
        and not any(w in _title(s).lower() for w in ("forced", "cc", "sdh"))
        and _title(s) != DUAL_TITLE
    ]
    return max(subs, key=lambda s: s["disposition"].get("default", 0), default=None)


def has_dual(all_streams: list[dict]) -> bool:
    return any(_title(s) == DUAL_TITLE for s in of_type(all_streams, "subtitle"))


def subtitle_text(mkv: Path, index: int) -> str:
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mkv), "-map", f"0:{index}", "-f", "ass", "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def write_dual(mkv: Path, out: Path, ass_file: Path, font: Path, all_streams: list[dict]) -> None:
    """Copy every stream, add the dual track and its font, and make it and Mandarin audio the defaults."""
    subs, audio = of_type(all_streams, "subtitle"), of_type(all_streams, "audio")
    n_attach = len(of_type(all_streams, "attachment"))
    zh = mandarin_audio(all_streams)
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(mkv),
        "-i",
        str(ass_file),
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
        "-attach",
        str(font),
        f"-metadata:s:t:{n_attach}",
        "mimetype=font/otf",
        f"-metadata:s:s:{len(subs)}",
        "language=eng",
        f"-metadata:s:s:{len(subs)}",
        f"title={DUAL_TITLE}",
        f"-disposition:s:{len(subs)}",
        "default",
    ]
    for i, s in enumerate(subs):  # drop default but keep forced, so signs-only tracks still work
        cmd += [f"-disposition:s:{i}", "forced" if s["disposition"].get("forced") else "0"]
    for i, a in enumerate(audio):
        cmd += [f"-disposition:a:{i}", "default" if a is zh else "0"]
    subprocess.run([*cmd, str(out)], check=True)
