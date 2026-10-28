"""Small document-viewing helpers used by the reviewer pilot."""

from pathlib import Path


def read_document(base_directory: str | Path, requested_path: str) -> str:
    """Read a document only when it remains inside base_directory."""
    base = Path(base_directory).resolve()
    target = (base / requested_path).resolve()
    if not target.is_relative_to(base):
        raise ValueError("requested path escapes the document directory")
    return target.read_text(encoding="utf-8")
