"""Testes para modules.structure_analysis (parsing ISO BMFF)."""
import struct
from pathlib import Path

from modules.structure_analysis import StructureAnalysisModule


def _atom(atom_type: str, payload: bytes = b"") -> bytes:
    """Monta um átomo ISO BMFF com header de 32 bits."""
    size = 8 + len(payload)
    return struct.pack(">I4s", size, atom_type.encode("ascii")) + payload


def _write_mp4(tmp_path: Path, *atoms: bytes) -> Path:
    file = tmp_path / "video.mp4"
    file.write_bytes(b"".join(atoms))
    return file


def test_parse_atoms_reads_top_level_sequence(case_manager, tmp_path: Path) -> None:
    file = _write_mp4(
        tmp_path,
        _atom("ftyp", b"isom" * 2),
        _atom("moov", b"\x00" * 16),
        _atom("mdat", b"\xff" * 32),
    )
    module = StructureAnalysisModule(case_manager)

    atoms = module._parse_atoms(file)

    assert [a["type"] for a in atoms] == ["ftyp", "moov", "mdat"]
    assert atoms[0]["offset"] == 0
    assert atoms[1]["offset"] == atoms[0]["size"]


def test_parse_atoms_handles_64bit_size(case_manager, tmp_path: Path) -> None:
    payload = b"\xab" * 8
    large_atom = (
        struct.pack(">I4s", 1, b"mdat")
        + struct.pack(">Q", 16 + len(payload))
        + payload
    )
    file = _write_mp4(tmp_path, _atom("ftyp"), large_atom)
    module = StructureAnalysisModule(case_manager)

    atoms = module._parse_atoms(file)

    assert atoms[1]["type"] == "mdat"
    assert atoms[1]["size"] == 16 + len(payload)


def test_parse_atoms_size_zero_extends_to_eof(case_manager, tmp_path: Path) -> None:
    open_ended = struct.pack(">I4s", 0, b"mdat") + b"\x00" * 100
    file = _write_mp4(tmp_path, _atom("ftyp"), open_ended)
    module = StructureAnalysisModule(case_manager)

    atoms = module._parse_atoms(file)

    assert atoms[-1]["type"] == "mdat"
    assert atoms[-1]["offset"] + atoms[-1]["size"] == file.stat().st_size


def test_parse_atoms_aborts_on_malformed_size(case_manager, tmp_path: Path) -> None:
    """Átomo com tamanho declarado menor que o header não pode causar loop infinito."""
    # size=4 é inválido (mínimo é 8): o parser deve parar sem travar.
    malformed = struct.pack(">I4s", 4, b"junk")
    file = _write_mp4(tmp_path, _atom("ftyp"), malformed, _atom("moov"))
    module = StructureAnalysisModule(case_manager)

    atoms = module._parse_atoms(file)

    # Apenas o ftyp válido antes do átomo malformado é retornado.
    assert [a["type"] for a in atoms] == ["ftyp"]


def test_fast_start_detected_when_moov_precedes_mdat(case_manager, tmp_path: Path) -> None:
    file = _write_mp4(tmp_path, _atom("ftyp"), _atom("moov"), _atom("mdat"))
    module = StructureAnalysisModule(case_manager)

    result = module.run(file, "structure.json")

    assert "Fast-Start" in result["analysis"]["conclusion"]


def test_capture_detected_when_mdat_precedes_moov(case_manager, tmp_path: Path) -> None:
    file = _write_mp4(tmp_path, _atom("ftyp"), _atom("mdat"), _atom("moov"))
    module = StructureAnalysisModule(case_manager)

    result = module.run(file, "structure.json")

    assert "Capture" in result["analysis"]["conclusion"]


def test_missing_moov_flagged_as_incomplete(case_manager, tmp_path: Path) -> None:
    file = _write_mp4(tmp_path, _atom("ftyp"), _atom("mdat"))
    module = StructureAnalysisModule(case_manager)

    result = module.run(file, "structure.json")

    assert "Incompleto" in result["analysis"]["conclusion"]


def test_run_saves_json_to_results_dir(case_manager, tmp_path: Path) -> None:
    file = _write_mp4(tmp_path, _atom("ftyp"), _atom("moov"), _atom("mdat"))
    module = StructureAnalysisModule(case_manager)

    module.run(file, "structure.json")

    assert (case_manager.results_dir / "structure.json").exists()


def test_run_returns_error_dict_for_missing_file(case_manager, tmp_path: Path) -> None:
    module = StructureAnalysisModule(case_manager)

    result = module.run(tmp_path / "inexistente.mp4", "structure.json")

    assert "error" in result
