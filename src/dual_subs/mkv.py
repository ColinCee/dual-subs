"""Read MKV streams with ffprobe and write the dual track into a copy with mkvmerge.

mkvmerge, not ffmpeg: ffmpeg wrote the added track's packets at the end of the file, so Plex,
which reads subtitles as it streams, showed none after a resume or seek.
"""

import json
import shutil
import subprocess
from pathlib import Path

CHINESE = {"chi", "zho", "cmn"}
DUAL_TITLE = "中文 + English"
MKVMERGE = shutil.which("mkvmerge") or "C:/Program Files/MKVToolNix/mkvmerge.exe"


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
    """Copy every stream, add the dual track and its font, and make it and Mandarin audio the defaults.

    Plex keeps a viewer's earlier track pick over these defaults; README.md says how to reset it.
    """
    zh = mandarin_audio(all_streams)
    # ffprobe's stream index is mkvmerge's track ID for MKV input; forced flags carry over untouched.
    flags = [f"{s['index']}:0" for s in of_type(all_streams, "subtitle")]
    flags += [f"{a['index']}:{int(a is zh)}" for a in of_type(all_streams, "audio")]
    cmd = [MKVMERGE, "-q", "-o", str(out)]
    for flag in flags:
        cmd += ["--default-track-flag", flag]
    cmd += [str(mkv), "--language", "0:eng", "--track-name", f"0:{DUAL_TITLE}"]
    cmd += ["--default-track-flag", "0:1", str(ass_file)]
    cmd += ["--attachment-name", font.name, "--attachment-mime-type", "font/otf", "--attach-file", str(font)]
    if subprocess.run(cmd, check=False).returncode > 1:  # 1 means warnings only
        raise SystemExit(f"mkvmerge failed on {mkv}")
