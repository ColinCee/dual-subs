# dual-subs

Adds a "中文 + English" subtitle track to MKV episodes so Plex shows both languages at once. The Chinese comes from transcribing each episode's Mandarin audio on the GPU; the English is the episode's own subtitles.

```bash
uv run dual-subs "E:/Plex/To Be Hero X/Season 01" --names names/to-be-hero-x.txt --backup "E:/dual-subs-originals/To Be Hero X/Season 01"
```

On a machine shared with other GPU jobs, run it under [`lease`](https://github.com/ColinCee/agents/blob/main/src/lease/lease.mts) so two jobs never hold the GPU at once (install: `npm run install-lease` in a clone of [ColinCee/agents](https://github.com/ColinCee/agents)):

```bash
lease run --name dual-subs --res gpu --for 7200 -- uv run dual-subs "E:/Plex/To Be Hero X/Season 01" --names names/to-be-hero-x.txt --backup "E:/dual-subs-originals/To Be Hero X/Season 01"
```

## Requirements

| Needs | Get it |
|---|---|
| An NVIDIA GPU, driver 570 or newer (CUDA 12.8) | [NVIDIA drivers](https://www.nvidia.com/en-us/drivers/) |
| Git | `winget install Git.Git` |
| [uv](https://docs.astral.sh/uv/) | `winget install astral-sh.uv` |
| `ffmpeg` and `ffprobe` | `winget install Gyan.FFmpeg` |
| [MKVToolNix](https://mkvtoolnix.download/) | `winget install MoritzBunkus.MKVToolNix` |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code), signed in | `npm install -g @anthropic-ai/claude-code` |

Tested on Windows only. Clone the repository and run from its root. The proofread runs `claude -p` on your own Claude login, so it uses your Claude usage; an episode whose proofread fails is skipped until the next run. The first run downloads the [FireRedASR2](https://github.com/FireRedTeam/FireRedASR2S) weights (about 6 GB, to `D:/models/fireredasr2s` or `DUAL_SUBS_MODELS`) and the Noto Sans SC font.

## How it works

Per episode:

1. Transcribes the Mandarin audio (`src/dual_subs/transcribe.py`; why this model: [docs/adr/0001-speech-to-text.md](docs/adr/0001-speech-to-text.md)).
2. Has Claude fix mishearings, using the English line and the show's cast list in `names/` (`proofread.py`).
3. Merges the Chinese into the English subtitles (`ass.py`).
4. Writes a checked copy with the new track as default, swaps it in and moves the original to `--backup`, which must be on the same drive so the swap is instant (`mkv.py`, `cli.py`).

Episodes already done, or without Mandarin audio or full English subtitles, are skipped, so re-running is safe. Transcripts and proofread lines are cached in `~/.cache/dual-subs/transcripts` and `proofread`, one per file name; delete one to redo that episode.

A new show gets its own `names/<show>.txt`, like [names/to-be-hero-x.txt](names/to-be-hero-x.txt).

## Plex

- Plex keeps each viewer's earlier subtitle pick over the new default. For episodes already watched, pick "中文 + English" once.
- The iPad and iPhone apps show only the English of this track. Setting Burn Subtitles to Always in the app's settings shows both, since the server then draws the subtitles onto the video; it re-encodes whenever subtitles are on.

## License

[MIT](LICENSE)
