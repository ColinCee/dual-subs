# dual-subs

Adds a combined Chinese + English subtitle track to MKV episodes from their Mandarin audio. How to run: `README.md`.

Checks: `uv run ruff check && uv run ruff format --check && uv run ty check`

| When | Read |
|---|---|
| Changing the speech-to-text model | `docs/adr/0001-speech-to-text.md` |
| Changing the subtitle layout | `src/dual_subs/ass.py` docstring |

## Rules

- Run it under the GPU lease: `lease run --name dual-subs --res gpu --for 3600 -- uv run dual-subs ...`.
- Write nothing into a media library folder until the copy passes `check()` in `src/dual_subs/cli.py`. Originals go to `--backup`, outside the library; deleting them waits for Colin.
- A new show gets `names/<show>.txt`: spellings from the show's Moegirl character list, plus each mishearing found in its transcripts.
