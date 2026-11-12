# dual-subs

Adds a "中文 + English" subtitle track to MKV episodes so Plex shows both languages at once. The Chinese comes from transcribing each episode's Mandarin audio on the GPU; the English is the episode's own subtitles.

```bash
uv run dual-subs "E:/Plex/To Be Hero X/Season 01" --names names/to-be-hero-x.txt --backup "E:/dual-subs-originals/To Be Hero X/Season 01"
```

Per episode it:

1. Transcribes the Mandarin audio with FireRedASR2 (model choice: [docs/adr/0001-speech-to-text.md](docs/adr/0001-speech-to-text.md)). Transcripts are cached in `~/.cache/dual-subs`.
2. Merges the Chinese lines into the English subtitles: Chinese pinned at the bottom, English lifted above it (`src/dual_subs/ass.py`).
3. Writes a copy with the new track, an attached Noto Sans SC font, the new track and the Mandarin audio as defaults, then swaps it in and moves the original to `--backup`.

Episodes already done, or without Mandarin audio or English subtitles, are skipped. Re-running is safe.

Needs an NVIDIA GPU, `ffmpeg` and `ffprobe` on PATH, and [uv](https://docs.astral.sh/uv/). Model weights (about 6 GB) download on first run to `D:/models/fireredasr2s`, or `DUAL_SUBS_MODELS`.
