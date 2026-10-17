from __future__ import annotations

from pathlib import Path

from ig_postprocess.media_index import MediaIndex, layout_rank


def _touch(root: Path, uri: str, content: bytes) -> None:
    path = root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_layout_rank_prefers_month_layout() -> None:
    assert layout_rank("media/posts/202501/1.jpg") < layout_rank("media/posts/1.jpg")


def test_preferred_picks_month_over_root(tmp_path: Path) -> None:
    _touch(tmp_path, "media/posts/1.jpg", b"same-bytes")
    _touch(tmp_path, "media/posts/202501/2.jpg", b"same-bytes")
    index = MediaIndex(tmp_path)
    chosen = index.preferred(["media/posts/1.jpg", "media/posts/202501/2.jpg"])
    assert chosen == "media/posts/202501/2.jpg"


def test_iter_files_hashes_every_file(tmp_path: Path) -> None:
    _touch(tmp_path, "media/posts/a.jpg", b"a")
    _touch(tmp_path, "media/posts/202501/b.jpg", b"b")
    index = MediaIndex(tmp_path)
    uris = {info.uri for info in index.iter_files("media")}
    assert uris == {"media/posts/a.jpg", "media/posts/202501/b.jpg"}
