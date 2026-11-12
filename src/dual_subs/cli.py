"""dual-subs PATH...: give every MKV a default "中文 + English" subtitle track.

Each episode: transcribe its Mandarin audio, have Claude fix mishearings (both cached), merge the
Chinese lines into its English subtitles, write a copy with the new track, then swap it in and
move the original to BACKUP.
"""

import argparse
import hashlib
import json
import tempfile
import urllib.request
from collections import Counter
from functools import partial
from pathlib import Path

from dual_subs import ass, mkv
from dual_subs.proofread import proofread

CACHE = Path.home() / ".cache" / "dual-subs"
# Pinned and hashed: the font is attached to every file written into the library.
FONT_URL = (
    "https://github.com/notofonts/noto-cjk/raw/165c01b46ea533872e002e0785ff17e44f6d97d8"
    "/Sans/SubsetOTF/SC/NotoSansSC-Medium.otf"
)
FONT_SHA256 = "7633f5a016d4dd95e685a69633d818aabc4644c4b08e26bd35b1b30c45ed5dda"


def load_names(path: Path | None) -> tuple[dict[str, str], list[str]]:
    """Fixes from lines of `heard=correct` (`萧月清=潇月卿`), and the cast: every correct name plus
    lines that are just a name. # starts a comment."""
    if path is None:
        return {}, []
    entries = [line.split("#")[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    fixes = dict(e.split("=", 1) for e in entries if "=" in e)
    cast = [e for e in entries if e and "=" not in e]
    return fixes, list(dict.fromkeys(cast + list(fixes.values())))


def cached_json(path: Path, make) -> list[dict]:
    """The JSON at path, made and saved first if missing; written whole or not at all."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        partial.write_text(json.dumps(make(), ensure_ascii=False), encoding="utf-8")
        partial.replace(path)
    return json.loads(path.read_text(encoding="utf-8"))


def show_title(video: Path) -> str:
    """'To Be Hero X - S01E01 - NICE' from the library layout Show/Season NN/file."""
    show = video.parent.parent.name if video.parent.name.lower().startswith("season") else video.parent.name
    return f"{show}: {video.stem}"


def font() -> Path:
    path = CACHE / "NotoSansSC-Medium.otf"
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != FONT_SHA256:
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(FONT_URL, timeout=120) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != FONT_SHA256:
            raise SystemExit(f"font download does not match its pinned hash: {FONT_URL}")
        path.write_bytes(data)
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("paths", type=Path, nargs="+", help="season folders or single .mkv files")
    p.add_argument("--names", type=Path, help="name fixes for this show, see names/")
    p.add_argument(
        "--backup", type=Path, required=True, help="where originals go; keep it outside the library"
    )
    args = p.parse_args()
    (names, cast), transcriber = load_names(args.names), None
    args.backup.mkdir(parents=True, exist_ok=True)

    videos = [v for p in args.paths for v in (sorted(p.glob("*.mkv")) if p.is_dir() else [p])]
    for video in videos:
        streams = mkv.streams(video)
        zh, en = mkv.mandarin_audio(streams), mkv.english_dialogue(streams)
        if mkv.has_dual(streams):
            print(f"skip (done): {video.name}")
            continue
        if zh is None or en is None:
            print(f"skip (no {'Mandarin audio' if zh is None else 'English subtitles'}): {video.name}")
            continue

        transcript = CACHE / "transcripts" / f"{video.stem}.json"
        if not transcript.exists() and transcriber is None:
            from dual_subs.transcribe import Transcriber

            transcriber = Transcriber()
        lines = cached_json(
            transcript, partial(transcriber.lines, video, zh["index"]) if transcriber else list
        )
        if not lines:
            print(f"skip (no Chinese heard): {video.name}")
            continue
        english = mkv.subtitle_text(video, en["index"])
        lines = cached_json(
            CACHE / "proofread" / f"{video.stem}.json",
            partial(proofread, lines, english, show_title(video), cast),
        )

        if video.resolve().drive != args.backup.resolve().drive:
            # Renames keep the swap instant; a cross-drive move leaves the episode missing from the
            # library for minutes, and the media server may drop it with its watch state.
            raise SystemExit(f"--backup must be on the same drive as {video}")
        if (args.backup / video.name).exists():
            raise SystemExit(f"a backup of {video.name} already exists in {args.backup}")
        dual = ass.merge(english, lines, names)
        # Built in the backup folder: outside the library, so the media server never scans a half-written file.
        with tempfile.TemporaryDirectory(dir=args.backup) as tmp:
            ass_file, out = Path(tmp) / "dual.ass", Path(tmp) / video.name
            ass_file.write_text(dual, encoding="utf-8")
            mkv.write_dual(video, out, ass_file, font(), streams)
            check(video, out, streams)
            video.rename(args.backup / video.name)
            out.rename(video)
        print(f"done: {video.name}")


def check(original: Path, out: Path, before: list[dict]) -> None:
    """Refuse to swap in a copy that lost a stream, a forced flag or playing time."""
    after = mkv.streams(out)
    kinds = Counter(s["codec_type"] for s in after)
    if kinds != Counter(s["codec_type"] for s in before) + Counter(["subtitle", "attachment"]):
        raise SystemExit(f"stream mismatch in {out}: {kinds}")
    defaults = [s for s in mkv.of_type(after, "subtitle") if s["disposition"].get("default")]
    if len(defaults) != 1 or not mkv.has_dual(defaults):
        raise SystemExit(f"dual track is not the one default subtitle in {out}")

    def forced(streams: list[dict]) -> list[tuple]:
        subs = mkv.of_type(streams, "subtitle")
        return [
            (s.get("tags", {}).get("language"), s.get("tags", {}).get("title"))
            for s in subs
            if s["disposition"].get("forced")
        ]

    if forced(after) != forced(before):
        raise SystemExit(f"forced flags changed in {out}")
    if abs(mkv.duration(original) - mkv.duration(out)) > 1:
        raise SystemExit(f"duration changed in {out}")


if __name__ == "__main__":
    main()
