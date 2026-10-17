"""Post-process an Instagram data export into per-post media folders.

The package is organised around three concerns:

* :mod:`ig_postprocess.export_reader` turns the raw JSON files into typed,
  text-repaired structures.
* :mod:`ig_postprocess.media_index` hashes media and resolves duplicate content
  to a single preferred file.
* :mod:`ig_postprocess.organize` plans and performs the on-disk layout.
"""

from __future__ import annotations

__version__ = "0.1.0"
