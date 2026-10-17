"""Cross-check the two export schemas against each other.

The newer ``posts.json`` is the superset, the legacy files are cleaner. Joining
them by shared media content must be one-to-one: every legacy post matches
exactly one entry, and no entry is claimed twice. Any deviation aborts the run
rather than silently producing a wrong layout.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .export_reader import LegacyPost, RawEntry
from .media_index import MediaIndex


class CrossCheckError(RuntimeError):
    """Raised when the two schemas disagree about posts or media."""


@dataclass(frozen=True)
class Match:
    """Bidirectional mapping between legacy posts and newer entries."""

    #: legacy index -> entry index
    legacy_to_entry: dict[int, int]
    #: entry index -> legacy index
    entry_to_legacy: dict[int, int]


def match_entries(
    entries: list[RawEntry],
    legacy_posts: list[LegacyPost],
    index: MediaIndex,
) -> Match:
    """Join legacy posts to newer entries by shared media content.

    Raises :class:`CrossCheckError` if the join is not a bijection, if a legacy
    post's media are not all present in its matched entry, or if totals differ.
    """
    content_to_entries: dict[str, set[int]] = {}
    for i, entry in enumerate(entries):
        for uri in entry.media_uris:
            digest = index.digest(uri)
            content_to_entries.setdefault(digest, set()).add(i)

    legacy_to_entry: dict[int, int] = {}
    claimed: dict[int, int] = {}
    for j, post in enumerate(legacy_posts):
        wanted = {index.digest(m.uri) for m in post.media}
        if not wanted:
            raise CrossCheckError(f"legacy post {j} ({post.source}) has no media")

        tally: Counter[int] = Counter()
        for digest in wanted:
            for i in content_to_entries.get(digest, ()):
                tally[i] += 1

        if not tally:
            raise CrossCheckError(f"legacy post {j} ({post.source}) matched no entry")

        best = max(tally.values())
        winners = [i for i, count in tally.items() if count == best]
        if len(winners) != 1:
            raise CrossCheckError(
                f"legacy post {j} ({post.source}) matched {len(winners)} entries ambiguously"
            )
        entry_index = winners[0]
        if best != len(wanted):
            raise CrossCheckError(
                f"legacy post {j} ({post.source}) shares only {best}/{len(wanted)} media "
                f"with entry {entry_index}"
            )
        if entry_index in claimed:
            raise CrossCheckError(
                f"entry {entry_index} claimed by both legacy posts {claimed[entry_index]} and {j}"
            )
        claimed[entry_index] = j
        legacy_to_entry[j] = entry_index

    if len(entries) != len(legacy_posts):
        raise CrossCheckError(
            f"entry count {len(entries)} != legacy post count {len(legacy_posts)}"
        )
    if len(claimed) != len(entries):
        raise CrossCheckError("some entries were not matched by any legacy post")

    entry_to_legacy = {v: k for k, v in legacy_to_entry.items()}
    return Match(legacy_to_entry=legacy_to_entry, entry_to_legacy=entry_to_legacy)
