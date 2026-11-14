# dual-subs

Adds a "中文 + English" subtitle track to MKV episodes so Plex shows both languages at once. The Chinese comes from transcribing each episode's Mandarin audio on the GPU; the English is the episode's own subtitles.

```bash
lease run --name dual-subs --res gpu --for 7200 -- uv run dual-subs "E:/Plex/To Be Hero X/Season 01" --names names/to-be-hero-x.txt --backup "E:/dual-subs-originals/To Be Hero X/Season 01"
```

Per episode it transcribes the Mandarin audio (`src/dual_subs/transcribe.py`; model choice in [docs/adr/0001-speech-to-text.md](docs/adr/0001-speech-to-text.md)), has Claude fix mishearings (`proofread.py`), merges the lines into the English subtitles (`ass.py`), writes a checked copy with the new track as default (`mkv.py`, `cli.py`), swaps it in and moves the original to `--backup`. Episodes already done, or without Mandarin audio or full English subtitles, are skipped, so re-running is safe.

Transcripts and proofread lines are cached in `~/.cache/dual-subs/transcripts` and `proofread`, one per file name. To redo an episode, delete its file there.

Plex keeps each viewer's earlier subtitle pick for an episode over the new default. For episodes already watched, pick "中文 + English" once in Plex.

On iPad the Plex app shows only the English of this track. Setting Burn Subtitles to Always in the app's settings shows both, since the server then draws the subtitles onto the video; it re-encodes the video whenever subtitles are on.

Needs an NVIDIA GPU, `ffmpeg`, `ffprobe`, [MKVToolNix](https://mkvtoolnix.download/) (`winget install MoritzBunkus.MKVToolNix`), the signed-in `claude` CLI and [uv](https://docs.astral.sh/uv/). The first run downloads the model weights (about 6 GB, to `D:/models/fireredasr2s` or `DUAL_SUBS_MODELS`) and the Noto Sans SC font.
