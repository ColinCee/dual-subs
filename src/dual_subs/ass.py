"""Merge timed Chinese lines into an existing English ASS script as one dual-language track.

Layout, as in bilingual fansubs: each Chinese line joins the English line it overlaps most, as one
event with the Chinese on top and the English smaller below, so both share the English timing.
Chinese with no English line under it shows on its own, in the same spot.
"""

import re
from collections import Counter

CN_FONT = "Noto Sans SC"
CN_STYLE = "Chinese"
EN_SCALE = 0.8  # English shrinks so the Chinese reads first
BS = "\\"


def _ts(seconds: float) -> str:
    cs = round(seconds * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _secs(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _play_res_y(script: str) -> int:
    m = re.search(r"^PlayResY:\s*(\d+)", script, re.MULTILINE)
    return int(m.group(1)) if m else 288  # the ASS default when PlayResY is absent


def fix_names(text: str, names: dict[str, str]) -> str:
    for wrong, right in names.items():
        text = text.replace(wrong, right)
    return text


def cap_repeats(text: str) -> str:
    """Cut a character repeated more than three times to three: the model sometimes loops on a
    sound (450 诶 in a row), which would fill the screen. Real stutters keep their feel."""
    return re.sub(r"(.)\1{3,}", r"\1\1\1", text)


def _is_dialogue(event: list[str]) -> bool:
    """Spoken lines, not signs: positioned text belongs to something on screen."""
    return not event[3].startswith("Sign") and f"{BS}pos" not in event[9] and f"{BS}move" not in event[9]


def merge(english_ass: str, lines: list[dict], names: dict[str, str]) -> str:
    res = _play_res_y(english_ass)
    size = round(res * 0.075)
    head, _, events_text = english_ass.partition("[Events]")
    events = [ln.split(",", 9) for ln in events_text.splitlines() if ln.startswith("Dialogue:")]
    dialogue = [e for e in events if _is_dialogue(e)]

    styles = {}

    def restyle(m: re.Match) -> str:
        fields = m.group(2).split(",")
        styles[fields[0]] = fields
        if not fields[0].startswith("Sign"):
            fields[2] = str(round(float(fields[2]) * EN_SCALE))  # Fontsize
        return m.group(1) + ",".join(fields)

    head = re.sub(r"^(Style:\s*)(.*)$", restyle, head, flags=re.MULTILINE)
    main = styles.get(Counter(e[3] for e in dialogue).most_common(1)[0][0]) if dialogue else None
    margin = main[21] if main else str(round(res * 0.05))
    head = re.sub(
        r"(^\[V4\+ Styles\]\nFormat:[^\n]*\n)",
        lambda m: (
            m.group(1)
            + f"Style: {CN_STYLE},{CN_FONT},{size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
            + f"0,0,0,0,100,100,0,0,1,{max(1, round(res / 180))},1,2,10,10,{margin},1\n"
        ),
        head,
        count=1,
        flags=re.MULTILINE,
    )

    chinese = [
        (float(ln["start"]), float(ln["end"]), cap_repeats(fix_names(ln["text"], names)).strip())
        for ln in lines
    ]
    chinese = [c for c in chinese if re.search(r"[一-鿿]", c[2])]  # drops English lyrics
    joined: dict[int, list[str]] = {}
    alone: list[tuple[float, float, str]] = []
    for start, end, text in chinese:
        overlaps = [(min(end, _secs(e[2])) - max(start, _secs(e[1])), i) for i, e in enumerate(dialogue)]
        best, at = max(overlaps, default=(0.0, -1))
        if best > 0:
            joined.setdefault(at, []).append(text)
        else:
            alone.append((start, end, text))

    cn_tags = "{" + f"{BS}fn{CN_FONT}{BS}fs{size}{BS}i0{BS}b0" + "}"
    for i, texts in joined.items():  # dialogue holds the same lists as events, so this edits events
        dialogue[i][9] = cn_tags + "".join(texts) + "{" + f"{BS}r" + "}" + f"{BS}N" + dialogue[i][9]
    body = [",".join(e) for e in events]
    body += [f"Dialogue: 0,{_ts(s)},{_ts(e)},{CN_STYLE},,0,0,0,,{t}" for s, e, t in alone]
    fmt = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    return head.rstrip("\n") + "\n\n[Events]\n" + fmt + "\n" + "\n".join(body) + "\n"
