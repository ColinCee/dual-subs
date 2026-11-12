"""Merge timed Chinese lines into an existing English ASS script as one dual-language track.

Layout: Chinese pinned at the bottom, bottom-anchored English styles lifted above it. Both
positions are fixed: letting the renderer stack overlapping lines swaps their order whenever the
Chinese line starts before the English one.
"""

import re

CN_FONT = "Noto Sans SC"
CN_STYLE = "Chinese"
MAX_CHARS = 20  # longer lines wrap to two rows and would run into the English above


def _ts(seconds: float) -> str:
    cs = round(seconds * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _play_res_y(script: str) -> int:
    m = re.search(r"^PlayResY:\s*(\d+)", script, re.MULTILINE)
    return int(m.group(1)) if m else 288  # the ASS default when PlayResY is absent


def fix_names(text: str, names: dict[str, str]) -> str:
    for wrong, right in names.items():
        text = text.replace(wrong, right)
    return text


def split_long(line: dict) -> list[dict]:
    """Split a long line at the punctuation nearest its middle, timing each part by its length."""
    text = line["text"]
    if len(text) <= MAX_CHARS:
        return [line]
    cuts = [i + 1 for i, ch in enumerate(text[:-1]) if ch in "，。？！、；：,.?!"]
    cut = min(cuts, key=lambda i: abs(i - len(text) / 2)) if cuts else len(text) // 2
    at = line["start"] + (line["end"] - line["start"]) * cut / len(text)
    return split_long({"start": line["start"], "end": at, "text": text[:cut]}) + split_long(
        {"start": at, "end": line["end"], "text": text[cut:]}
    )


def _lift_bottom_styles(script: str, lift: int) -> str:
    def lift_style(m: re.Match) -> str:
        fields = m.group(2).split(",")
        if fields[18].strip() in ("1", "2", "3"):  # Alignment: bottom row
            fields[21] = str(int(fields[21]) + lift)  # MarginV
        return m.group(1) + ",".join(fields)

    return re.sub(r"^(Style:\s*)(.*)$", lift_style, script, flags=re.MULTILINE)


def merge(english_ass: str, lines: list[dict], names: dict[str, str]) -> str:
    res = _play_res_y(english_ass)
    size, margin = round(res * 0.075), round(res * 0.04)
    script = _lift_bottom_styles(english_ass, lift=round(size * 1.2))
    style = (
        f"Style: {CN_STYLE},{CN_FONT},{size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
        f"0,0,0,0,100,100,0,0,1,{max(1, round(res / 180))},1,2,10,10,{margin},1"
    )
    script = re.sub(
        r"(^\[V4\+ Styles\]\nFormat:[^\n]*\n)",
        lambda m: m.group(1) + style + "\n",
        script,
        count=1,
        flags=re.MULTILINE,
    )
    events = []
    for line in lines:
        text = fix_names(line["text"], names).strip()
        if not re.search(r"[一-鿿]", text):
            continue  # English song lyrics and noise: the English track already covers lyrics
        for part in split_long(dict(line, text=text)):
            events.append(
                f"Dialogue: 1,{_ts(part['start'])},{_ts(part['end'])},{CN_STYLE},,0,0,0,,{part['text']}"
            )
    return script.rstrip("\n") + "\n" + "\n".join(events) + "\n"
