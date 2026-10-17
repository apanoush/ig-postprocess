# ig-postprocess

Turn an Instagram JSON data export into one folder per post.

The tool copies the read-only export into `post_processing/instagram_export/`
and then groups every photo, video and subtitle into
`<category>/<YYYY-MM-DD>_<post id>/` folders, together with a `caption.txt` and a
`post.json`. Duplicate media (the export stores the same image under two folder
layouts) are collapsed by content and the leftovers moved to `_duplicates/`.

## Usage

```bash
uv run ig-postprocess run        # copy (if needed), organise, write reports
uv run ig-postprocess copy       # only copy the export
uv run ig-postprocess organize   # organise an existing copy
uv run ig-postprocess report     # regenerate reports from an organised tree
```

Add `--force` to refresh an existing copy.

## Output layout

```
post_processing/instagram_export/
  posts/<YYYY-MM-DD>_<post id>/
    01_<media id>.jpg
    02_<media id>.mp4
    02_<media id>.srt
    caption.txt          # only when the post has a caption
    post.json
  archived_posts/  stories/  profile/
  saved/                 # saved-posts metadata (no media)
  _duplicates/           # byte-identical leftovers, safe to delete
  your_instagram_activity/media/*.json
  index.csv
  duplicates_report.json
  summary.md
```

## Why two post files

The export contains two schema generations. `posts_1.json` (plus
`archived_posts.json`) is the legacy, clean format; `posts.json` is the newer,
nested, localized format and is the complete superset. The two are
cross-checked against each other: media order and captions come from the legacy
files, while the newer schema supplies extra cover images and `.srt` subtitles.

## Design

See `doc/index.md`.
