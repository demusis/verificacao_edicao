"""Testes para core.logger (auditoria com hash chain)."""
import json
from pathlib import Path

from core.logger import GENESIS_HASH, Logger


def _make_logger(tmp_path: Path) -> Logger:
    return Logger(tmp_path / "execution.log")


def test_log_writes_jsonl_event(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    logger.log("START_MODULE", {"module": "FileAnalysis"})

    events = logger.read_events()
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "START_MODULE"
    assert event["details"] == {"module": "FileAnalysis"}
    assert "timestamp" in event


def test_log_without_details_uses_empty_dict(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    logger.log("PING")

    assert logger.read_events()[0]["details"] == {}


def test_first_event_chains_from_genesis(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    logger.log("A")

    assert logger.read_events()[0]["prev_hash"] == GENESIS_HASH


def test_chain_is_valid_after_multiple_events(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    for i in range(5):
        logger.log("EVENT", {"index": i})

    report = logger.verify_chain()
    assert report["valid"] is True
    assert report["total_events"] == 5
    assert report["verified_events"] == 5
    assert report["legacy_events"] == 0


def test_chain_resumes_across_logger_instances(tmp_path: Path) -> None:
    log_path = tmp_path / "execution.log"
    Logger(log_path).log("FIRST")
    Logger(log_path).log("SECOND")

    report = Logger(log_path).verify_chain()
    assert report["valid"] is True
    assert report["verified_events"] == 2


def test_tampered_event_content_is_detected(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    logger.log("HASH_CALC", {"hash": "abc123"})
    logger.log("DONE")

    lines = logger.log_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["details"]["hash"] = "FORJADO"
    lines[0] = json.dumps(tampered, ensure_ascii=False)
    logger.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = logger.verify_chain()
    assert report["valid"] is False
    assert any("alterado" in e["reason"] for e in report["errors"])


def test_deleted_event_breaks_chain(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    for i in range(3):
        logger.log("EVENT", {"index": i})

    lines = logger.log_path.read_text(encoding="utf-8").splitlines()
    del lines[1]  # remove evento do meio
    logger.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert logger.verify_chain()["valid"] is False


def test_reordered_events_break_chain(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    logger.log("A")
    logger.log("B")

    lines = logger.log_path.read_text(encoding="utf-8").splitlines()
    lines.reverse()
    logger.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert logger.verify_chain()["valid"] is False


def test_legacy_events_are_tolerated(tmp_path: Path) -> None:
    log_path = tmp_path / "execution.log"
    legacy = {"timestamp": "2025-01-01T00:00:00", "event_type": "OLD", "details": {}}
    log_path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    logger = Logger(log_path)
    logger.log("NEW_EVENT")

    report = logger.verify_chain()
    assert report["valid"] is True
    assert report["legacy_events"] == 1
    assert report["verified_events"] == 1


def test_read_events_skips_corrupted_lines(tmp_path: Path) -> None:
    logger = _make_logger(tmp_path)
    logger.log("VALID")
    with open(logger.log_path, "a", encoding="utf-8") as f:
        f.write("{linha quebrada\n")

    events = logger.read_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "VALID"
