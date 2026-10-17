from __future__ import annotations

from ig_postprocess.textfix import fix_mojibake


def test_repairs_double_encoded_german() -> None:
    assert fix_mojibake("VerÃ¶ffentlicht") == "Veröffentlicht"
    assert fix_mojibake("DateigrÃ¶Ã\x9fe in Bytes") == "Dateigröße in Bytes"


def test_repairs_double_encoded_emoji() -> None:
    assert fix_mojibake("ð\x9f\x98³") == "😳"


def test_leaves_valid_text_untouched() -> None:
    assert fix_mojibake("café") == "café"
    assert fix_mojibake("plain ascii") == "plain ascii"
    assert fix_mojibake("") == ""
