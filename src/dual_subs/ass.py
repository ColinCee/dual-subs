"""Merge timed Chinese lines into an existing English ASS script as one dual-language track.

Layout, as in bilingual fansubs: one row of Chinese on top and the English smaller below, capped in
width. Each Chinese line joins the English line it overlaps most; when several Chinese rows fall in
one English line, they take turns, each shown from when it is spoken. Chinese with no English line
under it shows on its own, in the same spot.
"""

import re
from collections import Counter

CN_FONT = "Noto Sans SC"
CN_STYLE = "Chinese"
EN_SCALE = 0.8  # English shrinks so the Chinese reads first
SIDE_MARGIN = 0.12  # of the frame width on each side: caps how wide a line runs
MIN_TURN = 0.8  # seconds; a shorter Chinese turn flashes by before it can be read
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


def plain(text: str) -> str:
    """Text safe inside one ASS event: no override braces, escapes or line breaks. Chinese lines
    come from models (a transcriber and Claude), so treat them as untrusted."""
    return re.sub(r"[{}\\\x00-\x1f\x7f]", "", text)


Piece = tuple[float, float, str]


def pieces(piece: Piece, limit: int) -> list[Piece]:
    """A line cut into one-row pieces of at most limit characters, at the punctuation nearest the
    middle, each timed by its share of the characters. The renderer only wraps at spaces, and
    Chinese has none; one row at a time keeps a long speech from stacking up the screen."""
    start, end, text = piece
    if len(text) <= limit:
        return [piece]
    cuts = [i + 1 for i, ch in enumerate(text[:-1]) if ch in "，。？！、；：,.?!"]
    cut = min(cuts, key=lambda i: abs(i - len(text) / 2)) if cuts else len(text) // 2
    at = start + (end - start) * cut / len(text)
    return pieces((start, at, text[:cut]), limit) + pieces((at, end, text[cut:]), limit)


def _turns(cue_start: float, cue_end: float, chinese: list[Piece], limit: int) -> list[Piece]:
    """The English cue cut into turns, one per Chinese piece: each piece shows from when it is
    spoken until the next one starts, inside the cue. A turn too short to read joins a neighbour
    when the two fit in one row."""
    starts = [cue_start] + [min(max(p[0], cue_start), cue_end) for p in chinese[1:]]
    starts = [max(starts[: k + 1]) for k in range(len(starts))]  # never step back in time
    ends = starts[1:] + [cue_end]
    turns = [(s, e, p[2]) for s, e, p in zip(starts, ends, chinese, strict=True) if e > s]
    merged: list[Piece] = []
    for s, e, text in turns:
        prev = merged[-1] if merged else None
        short = e - s < MIN_TURN or (prev is not None and prev[1] - prev[0] < MIN_TURN)
        if prev and short and len(prev[2]) + len(text) <= limit:
            merged[-1] = (prev[0], e, prev[2] + text)
        else:
            merged.append((s, e, text))
    return merged


def _is_dialogue(event: list[str]) -> bool:
    """Spoken lines, not signs: positioned text belongs to something on screen."""
    return not event[3].startswith("Sign") and f"{BS}pos" not in event[9] and f"{BS}move" not in event[9]


def merge(english_ass: str, lines: list[dict], names: dict[str, str]) -> str:
    res = _play_res_y(english_ass)
    size = round(res * 0.075)
    m = re.search(r"^PlayResX:\s*(\d+)", english_ass, re.MULTILINE)
    width = int(m.group(1)) if m else res * 4 // 3  # libass's default when PlayResX is absent
    side = round(width * SIDE_MARGIN)
    per_row = (width - 2 * side) // size
    head, _, events_text = english_ass.partition("[Events]")
    events = [ln.split(",", 9) for ln in events_text.splitlines() if ln.startswith("Dialogue:")]
    dialogue = [e for e in events if _is_dialogue(e)]

    styles = {}

    def restyle(m: re.Match) -> str:
        fields = m.group(2).split(",")
        styles[fields[0]] = fields
        if not fields[0].startswith("Sign"):
            fields[2] = str(round(float(fields[2]) * EN_SCALE))  # Fontsize
            fields[19] = fields[20] = str(side)  # MarginL, MarginR
        return m.group(1) + ",".join(fields)

    head = re.sub(r"^(Style:\s*)(.*)$", restyle, head, flags=re.MULTILINE)
    main = styles.get(Counter(e[3] for e in dialogue).most_common(1)[0][0]) if dialogue else None
    margin = main[21] if main else str(round(res * 0.05))
    head = re.sub(
        r"(^\[V4\+ Styles\]\nFormat:[^\n]*\n)",
        lambda m: (
            m.group(1)
            + f"Style: {CN_STYLE},{CN_FONT},{size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
            + f"0,0,0,0,100,100,0,0,1,{max(1, round(res / 180))},1,2,{side},{side},{margin},1\n"
        ),
        head,
        count=1,
        flags=re.MULTILINE,
    )

    chinese = [
        (float(ln["start"]), float(ln["end"]), plain(cap_repeats(fix_names(ln["text"], names))).strip())
        for ln in lines
    ]
    chinese = [c for c in chinese if re.search(r"[一-鿿]", c[2])]  # drops English lyrics
    joined: dict[int, list[Piece]] = {}
    alone: list[Piece] = []
    for line in chinese:
        start, end, _ = line
        overlaps = [(min(end, _secs(e[2])) - max(start, _secs(e[1])), i) for i, e in enumerate(dialogue)]
        best, at = max(overlaps, default=(0.0, -1))
        (joined.setdefault(at, []) if best > 0 else alone).extend(pieces(line, per_row))

    # The release's hard breaks were set for the larger size; the margins now decide where English wraps.
    for e in dialogue:
        e[9] = re.sub(rf" *{re.escape(BS)}N *", " ", e[9])
    cn_tags = "{" + f"{BS}fn{CN_FONT}{BS}fs{size}{BS}i0{BS}b0" + "}"
    paired = {id(dialogue[i]): chinese for i, chinese in joined.items()}
    body = []
    for e in events:
        if id(e) not in paired:
            body.append(",".join(e))
            continue
        for s, end, text in _turns(_secs(e[1]), _secs(e[2]), sorted(paired[id(e)]), per_row):
            turn = [
                *e[:1],
                _ts(s),
                _ts(end),
                *e[3:9],
                cn_tags + text + "{" + f"{BS}r" + "}" + f"{BS}N" + e[9],
            ]
            body.append(",".join(turn))
    body += [f"Dialogue: 0,{_ts(s)},{_ts(e)},{CN_STYLE},,0,0,0,,{t}" for s, e, t in alone]
    fmt = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    return head.rstrip("\n") + "\n\n[Events]\n" + fmt + "\n" + "\n".join(body) + "\n"
