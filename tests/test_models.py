"""What someone running a read is told when the server program or the model file is missing:
a plain sentence saying what to do, never a bare operating-system error."""

import sys
from pathlib import Path

import pytest

from inspection_reader import models

ITEM = {"file": "model.gguf", "source": "someone/model-GGUF", "bytes": 3, "sha256": "x"}


def test_a_missing_server_program_says_how_to_provide_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LLAMA_SERVER", str(tmp_path / "no-such-llama-server"))
    with pytest.raises(SystemExit, match="put llama.cpp's llama-server on PATH, or set"):
        models.server_program()


def test_a_server_program_given_by_its_path_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_SERVER", sys.executable)
    assert Path(models.server_program()) == Path(sys.executable)


def test_a_missing_model_file_says_where_to_get_it(tmp_path: Path) -> None:
    (problem,) = models.problems([ITEM], tmp_path, quick=True)
    assert "missing:" in problem
    assert "https://huggingface.co/someone/model-GGUF" in problem


def test_a_model_file_of_the_wrong_size_is_refused(tmp_path: Path) -> None:
    (tmp_path / "model.gguf").write_bytes(b"four")
    assert models.problems([ITEM], tmp_path, quick=True) == ["size differs: model.gguf"]
