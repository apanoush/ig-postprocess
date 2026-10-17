"""Repair text that an Instagram export double-encoded as UTF-8 bytes in Latin-1."""

from __future__ import annotations


def fix_mojibake(text: str) -> str:
    """Undo one layer of mojibake on *text*.

    The export stores captions and labels as UTF-8 bytes that were decoded as
    Latin-1 and re-encoded, so ``"VerÃ¶ffentlicht"`` appears instead of
    ``"Veröffentlicht"``. The inverse transform is ``encode("latin-1")`` followed
    by ``decode("utf-8")``.

    Text that is not valid mojibake, or that contains characters outside the
    Latin-1 range, is returned unchanged. Applying the function to already
    correct text is therefore safe.
    """
    if not text:
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired
