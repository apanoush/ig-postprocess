from __future__ import annotations

import json
from pathlib import Path

from ig_postprocess.export_reader import (
    read_archived_posts,
    read_legacy_posts,
    read_new_entries,
    read_profile_photos,
    read_stories,
)


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_read_new_entries_collects_nested_media_in_order(tmp_path: Path) -> None:
    payload = [
        {
            "timestamp": 100,
            "fbid": "42",
            "media": [],
            "label_values": [
                {"label": "Untertitel", "value": "hello"},
                {
                    "label": "Medien",
                    "media": [{"uri": "media/posts/42.jpg"}, {"uri": "media/posts/202501/1.jpg"}],
                },
                {
                    "dict": [
                        {"label": "Medien", "media": [{"uri": "media/posts/202501/2.mp4"}]},
                    ],
                    "title": "Medien",
                },
            ],
        }
    ]
    entries = read_new_entries(_write(tmp_path / "posts.json", payload))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.fbid == "42"
    assert entry.caption == "hello"
    assert entry.media_uris == (
        "media/posts/42.jpg",
        "media/posts/202501/1.jpg",
        "media/posts/202501/2.mp4",
    )


def test_read_new_entries_accepts_single_object(tmp_path: Path) -> None:
    payload = {"timestamp": 1, "fbid": "7", "label_values": [{"label": "Medien", "media": []}]}
    entries = read_new_entries(_write(tmp_path / "other_content.json", payload))
    assert [e.fbid for e in entries] == ["7"]


def test_read_legacy_posts_text_is_repaired(tmp_path: Path) -> None:
    payload = [
        {
            "media": [{"uri": "media/posts/1.jpg", "title": "x"}],
            "title": "cafÃ©",
            "creation_timestamp": 5,
        }
    ]
    posts = read_legacy_posts(_write(tmp_path / "posts_1.json", payload))
    assert posts[0].caption == "café"
    assert posts[0].media[0].uri == "media/posts/1.jpg"


def test_read_archived_posts_uses_media_title(tmp_path: Path) -> None:
    payload = {
        "ig_archived_post_media": [
            {
                "media": [
                    {
                        "uri": "media/archived_posts/202301/9.jpg",
                        "title": "old post",
                        "creation_timestamp": 3,
                    }
                ]
            }
        ]
    }
    posts = read_archived_posts(_write(tmp_path / "archived_posts.json", payload))
    assert posts[0].caption == "old post"
    assert posts[0].timestamp == 3


def test_read_stories_and_profile(tmp_path: Path) -> None:
    stories = read_stories(
        _write(tmp_path / "stories.json", {"ig_stories": [{"uri": "media/stories/202303/a.jpg"}]})
    )
    profile = read_profile_photos(
        _write(
            tmp_path / "profile_photos.json",
            {"ig_profile_picture": [{"uri": "media/posts/p.jpg"}]},
        )
    )
    assert stories[0].uri == "media/stories/202303/a.jpg"
    assert profile[0].uri == "media/posts/p.jpg"
