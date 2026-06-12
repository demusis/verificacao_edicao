"""Testes para core.hashing (integridade de arquivos)."""
import hashlib
from pathlib import Path

from core.hashing import calculate_file_hash


def _write(tmp_path: Path, content: bytes) -> Path:
    file = tmp_path / "evidencia.bin"
    file.write_bytes(content)
    return file


def test_sha512_matches_hashlib(tmp_path: Path) -> None:
    content = b"conteudo de evidencia forense"
    file = _write(tmp_path, content)

    assert calculate_file_hash(file) == hashlib.sha512(content).hexdigest()


def test_alternative_algorithm(tmp_path: Path) -> None:
    content = b"abc"
    file = _write(tmp_path, content)

    assert calculate_file_hash(file, algorithm="sha256") == hashlib.sha256(content).hexdigest()


def test_chunk_size_does_not_affect_result(tmp_path: Path) -> None:
    content = bytes(range(256)) * 100
    file = _write(tmp_path, content)

    assert calculate_file_hash(file, chunk_size=3) == calculate_file_hash(file, chunk_size=8192)


def test_empty_file(tmp_path: Path) -> None:
    file = _write(tmp_path, b"")

    assert calculate_file_hash(file) == hashlib.sha512(b"").hexdigest()


def test_accepts_string_path(tmp_path: Path) -> None:
    content = b"caminho como string"
    file = _write(tmp_path, content)

    assert calculate_file_hash(str(file)) == hashlib.sha512(content).hexdigest()
