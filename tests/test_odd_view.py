from pathlib import Path

import pytest

from odd_view import read_document


def test_reads_document_inside_base(tmp_path: Path):
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    assert read_document(tmp_path, "note.txt") == "hello"


def test_rejects_parent_traversal(tmp_path: Path):
    documents = tmp_path / "documents"
    documents.mkdir()
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        read_document(documents, "../secret.txt")
