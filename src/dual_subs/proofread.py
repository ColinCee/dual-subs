"""Fix speech-recognition mistakes in the Chinese lines with Claude, using the English as context.

Runs the Claude Code CLI (`claude -p`), so it uses the signed-in Claude subscription; no API key.
"""

import json
import re
import subprocess

from dual_subs.ass import BS, _secs

PROMPT = """You proofread a machine transcript of the Mandarin audio of an anime episode ({title}).
Each item has the transcribed Chinese ("zh") and the official English subtitle on screen at that moment ("en").
Character names in this show: {cast}

Fix only speech-recognition mistakes: a wrong character that sounds the same or nearly the same,
a misheard name, a garbled word that the context makes clear. Keep everything else as spoken:
the speaker's own wording, fillers, stutters and repetitions. Never rephrase, never translate from
the English, never add speech that is missing, and leave punctuation alone. When unsure, change nothing.

Reply with JSON only, listing just the lines you changed:
{{"fixes": [{{"i": <item number>, "zh": "<corrected line>"}}]}}

Items:
{items}"""


def _english_at(start: float, end: float, events: list[list[str]]) -> str:
    texts = [e[9] for e in events if min(end, _secs(e[2])) - max(start, _secs(e[1])) > 0]
    return re.sub(r"\{[^}]*\}", "", " ".join(texts)).replace(f"{BS}N", " ").strip()


def proofread(lines: list[dict], english_ass: str, title: str, cast: list[str]) -> list[dict]:
    """The lines with Claude's fixes applied; each changed line keeps its timing."""
    events = [ln.split(",", 9) for ln in english_ass.splitlines() if ln.startswith("Dialogue:")]
    items = [
        {"i": i, "zh": ln["text"], "en": _english_at(ln["start"], ln["end"], events)}
        for i, ln in enumerate(lines)
        if re.search(r"[一-鿿]", ln["text"])
    ]
    prompt = PROMPT.format(
        title=title,
        cast="、".join(cast) or "(none given)",
        items="\n".join(json.dumps(it, ensure_ascii=False) for it in items),
    )
    out = subprocess.run(
        ["claude", "-p", "--output-format", "json", "--tools", ""],  # text in, text out: no tools
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=1800,
    )
    reply = json.loads(out.stdout)["result"]
    fixes = json.loads(reply[reply.index("{") : reply.rindex("}") + 1]).get("fixes") or []
    fixed = [dict(ln) for ln in lines]
    for fix in fixes:
        i, zh = (
            fix.get("i") if isinstance(fix, dict) else None,
            fix.get("zh") if isinstance(fix, dict) else None,
        )
        if isinstance(i, int) and 0 <= i < len(fixed) and isinstance(zh, str) and zh.strip():
            fixed[i]["text"] = zh
    return fixed
