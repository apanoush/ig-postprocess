from __future__ import annotations

from pathlib import Path

import pytest

from ig_postprocess.crosscheck import CrossCheckError, match_entries
from ig_postprocess.export_reader import LegacyPost, MediaRef, RawEntry
from ig_postprocess.media_index import MediaIndex
from ig_postprocess.organize import plan_posts


def _touch(root: Path, uri: str, content: bytes) -> None:
    path = root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _entry(fbid: str, uris: list[str], timestamp: int = 1_700_000_000) -> RawEntry:
    return RawEntry(
        fbid=fbid, timestamp=timestamp, media_uris=tuple(uris), caption="", source="posts.json"
    )


def _legacy(uris: list[str], caption: str = "", timestamp: int = 1_700_000_000) -> LegacyPost:
    return LegacyPost(
        media=tuple(MediaRef(uri=u) for u in uris),
        timestamp=timestamp,
        caption=caption,
        source="posts_1.json",
    )


def test_plan_prepends_unique_cover_and_appends_subtitles(tmp_path: Path) -> None:
    files = {
        "media/posts/999.jpg": b"Z",  # unique cover, named after fbid
        "media/posts/100.jpg": b"X",
        "media/posts/202501/200.jpg": b"Y",
        "media/posts/202501/201.srt": b"sub",
    }
    for uri, content in files.items():
        _touch(tmp_path, uri, content)
    index = MediaIndex(tmp_path)

    entry = _entry(
        "999",
        [
            "media/posts/999.jpg",
            "media/posts/100.jpg",
            "media/posts/202501/200.jpg",
            "media/posts/202501/201.srt",
        ],
    )
    legacy = _legacy(["media/posts/202501/200.jpg", "media/posts/100.jpg"], caption="hello")

    posts = plan_posts([entry], [legacy], [], index, "%Y-%m-%d")
    assert len(posts) == 1
    post = posts[0]
    assert post.folder == "2023-11-14_999"
    assert post.caption == "hello"
    assert post.caption_source == "posts_1.json"
    assert [m.filename for m in post.media] == [
        "01_999.jpg",
        "02_200.jpg",
        "03_100.jpg",
        "04_201.srt",
    ]


def test_plan_dedupes_content_and_prefers_month_layout(tmp_path: Path) -> None:
    files = {
        "media/posts/100.jpg": b"X",
        "media/posts/202501/500.jpg": b"X",  # same content, newer layout
        "media/posts/202501/200.jpg": b"Y",
    }
    for uri, content in files.items():
        _touch(tmp_path, uri, content)
    index = MediaIndex(tmp_path)

    entry = _entry(
        "42", ["media/posts/100.jpg", "media/posts/202501/200.jpg", "media/posts/202501/500.jpg"]
    )
    legacy = _legacy(["media/posts/100.jpg", "media/posts/202501/200.jpg"])

    posts = plan_posts([entry], [legacy], [], index, "%Y-%m-%d")
    names = [m.filename for m in posts[0].media]
    # 100.jpg and 500.jpg share content, so only one survives: the month copy.
    assert names == ["01_500.jpg", "02_200.jpg"]


def test_match_entries_rejects_mismatch(tmp_path: Path) -> None:
    _touch(tmp_path, "media/posts/1.jpg", b"A")
    _touch(tmp_path, "media/posts/2.jpg", b"B")
    index = MediaIndex(tmp_path)
    entries = [_entry("1", ["media/posts/1.jpg"])]
    legacy = [_legacy(["media/posts/1.jpg", "media/posts/2.jpg"])]
    with pytest.raises(CrossCheckError):
        match_entries(entries, legacy, index)


def test_match_entries_requires_bijection(tmp_path: Path) -> None:
    _touch(tmp_path, "media/posts/1.jpg", b"A")
    _touch(tmp_path, "media/posts/2.jpg", b"B")
    index = MediaIndex(tmp_path)
    entries = [_entry("1", ["media/posts/1.jpg"]), _entry("2", ["media/posts/2.jpg"])]
    legacy = [_legacy(["media/posts/1.jpg"])]
    with pytest.raises(CrossCheckError):
        match_entries(entries, legacy, index)
