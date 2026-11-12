"""dual-subs PATH...: give every MKV a default "中文 + English" subtitle track.

Each episode: transcribe its Mandarin audio (cached), merge the Chinese lines into its English
subtitles, write a copy with the new track, then swap it in and move the original to BACKUP.
"""

import argparse
import json
import shutil
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path

from dual_subs import ass, mkv

CACHE = Path.home() / ".cache" / "dual-subs"
FONT_URL = "https://github.com/notofonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-Medium.otf"


def load_names(path: Path | None) -> dict[str, str]:
    """Lines of `heard=correct`, e.g. `萧月清=潇月卿`; # starts a comment."""
    if path is None:
        return {}
    pairs = (line.split("#")[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return dict(p.split("=", 1) for p in pairs if p)


def font() -> Path:
    path = CACHE / "NotoSansSC-Medium.otf"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(FONT_URL, path)
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("paths", type=Path, nargs="+", help="season folders or single .mkv files")
    p.add_argument("--names", type=Path, help="name fixes for this show, see names/")
    p.add_argument(
        "--backup", type=Path, required=True, help="where originals go; keep it outside the library"
    )
    args = p.parse_args()
    names, transcriber = load_names(args.names), None

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

        cached = CACHE / "transcripts" / f"{video.stem}.json"
        if not cached.exists():
            if transcriber is None:
                from dual_subs.transcribe import Transcriber

                transcriber = Transcriber()
            cached.parent.mkdir(parents=True, exist_ok=True)
            lines = transcriber.lines(video, zh["index"])
            cached.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
        lines = json.loads(cached.read_text(encoding="utf-8"))

        dual = ass.merge(mkv.subtitle_text(video, en["index"]), lines, names)
        args.backup.mkdir(parents=True, exist_ok=True)
        # Built in the backup folder: outside the library, so the media server never scans a half-written file.
        with tempfile.TemporaryDirectory(dir=args.backup) as tmp:
            ass_file, out = Path(tmp) / "dual.ass", Path(tmp) / video.name
            ass_file.write_text(dual, encoding="utf-8")
            mkv.write_dual(video, out, ass_file, font(), streams)
            check(video, out, streams)
            shutil.move(video, args.backup / video.name)
            shutil.move(out, video)
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
