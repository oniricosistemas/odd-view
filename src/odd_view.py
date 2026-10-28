"""Small document-viewing helpers used by the reviewer pilot."""

from pathlib import Path


def read_document(base_directory: str | Path, requested_path: str) -> str:
    """Read a requested document from base_directory."""
    target = Path(base_directory) / requested_path
    return target.read_text(encoding="utf-8")
