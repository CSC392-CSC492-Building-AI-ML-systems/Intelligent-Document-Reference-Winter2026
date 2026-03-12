"""Tests for processing engine."""

from app.core.engine import ProcessingEngine


def test_empty_pipeline():
    engine = ProcessingEngine(config={})
    assert engine.run("hello") == "hello"


def test_single_stage():
    engine = ProcessingEngine(config={})
    engine.add_stage(str.upper)
    assert engine.run("hello") == "HELLO"


def test_multiple_stages():
    engine = ProcessingEngine(config={})
    engine.add_stage(str.upper)
    engine.add_stage(lambda s: s.replace("O", "0"))
    assert engine.run("hello") == "HELL0"
