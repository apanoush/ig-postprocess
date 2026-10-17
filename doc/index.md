# ig-postprocess

## Responsibility

Post-process an Instagram JSON data export into one folder per post, so the
media can be browsed and reused instead of living in a flat, duplicated tree.

## Pipeline

1. **copy** (`organize.copy_export`) copies `media/` and
   `your_instagram_activity/` from the read-only export into
   `post_processing/instagram_export/`. Unrelated files next to the export are
   never touched.
2. **hash** (`media_index.MediaIndex`) MD5-hashes every media file so duplicate
   content can be recognised even when the file names differ.
3. **read** (`export_reader`) parses both schema generations into typed
   structures and repairs double-encoded text (`textfix.fix_mojibake`).
4. **cross-check** (`crosscheck.match_entries`) joins legacy posts to newer
   entries by shared media content. The join must be one-to-one; any mismatch
   aborts the run.
5. **plan** (`organize.plan_posts`, `organize.plan_singles`) decides folder
   names, media order and captions.
6. **move** (`organize.organize`) moves media into the post folders, writes
   `caption.txt` and `post.json`, and relocates leftover files to
   `_duplicates/`.
7. **report** (`report.write_reports`) writes `index.csv`,
   `duplicates_report.json` and `summary.md`.

## Key data structures

* `export_reader.RawEntry` / `LegacyPost` / `MediaRef`: text-repaired views of
  the export JSON.
* `media_index.FileInfo`: URI, MD5, size and layout rank of one file.
* `organize.PlannedPost` / `PlannedMedia` / `PlannedSingle`: the target layout,
  independent of the filesystem, so it is easy to reason about and test.

## Decisions

### Two schemas, cross-checked

The export ships `posts.json` (newer, nested, localized) and `posts_1.json`
(legacy, clean) alongside each other; the newer one is the superset. Media
*order* and *captions* come from the legacy files, because the newer schema's
recursive order does not match the true carousel order and its labels are
localized. The newer schema is used only to recover media the legacy files omit
(cover images, `.srt` subtitles). `crosscheck` guarantees the two agree.

### Duplicates by content, not by name

The export keeps two media layouts, so the same image exists under two
different IDs. Files are identified by MD5; within a post one file per content
is kept, preferring the newer `media/posts/<YYYYMM>/` layout. The 4 images that
are genuinely reused across two different posts stay in both post folders. All
remaining byte-identical copies are moved to `_duplicates/` (reported, never
silently deleted).

### Mojibake repair

All text in the export is double-encoded UTF-8. `fix_mojibake` reverses one
layer and is a no-op on text that is not mojibake, making it safe to apply
everywhere.

## Alternatives considered

* **Use `posts.json` alone as the post source.** Rejected: its recursive media
  order does not match the true carousel order and it duplicates each image
  under two layouts.
* **Use `posts_1.json` alone.** Rejected: it is a strict subset, missing the 16
  archived posts, cover images and subtitles.
* **Delete duplicate files outright.** Rejected in favour of moving them to
  `_duplicates/`, so the operation stays reversible.
