from pathlib import Path

COMMON_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "utf-16")


def decode_bill(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in COMMON_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    # Preserve row boundaries for an actionable parse error. The replacement
    # characters are detected by the parser as malformed content where needed.
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"
