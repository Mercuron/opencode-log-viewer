from __future__ import annotations

from viewer.importers.inference_log import correlate_and_store, parse_llama_server_log
from viewer.ingest import write_batch

from .conftest import load_fixture_events

SAMPLE_LOG = """
[2026-08-10T14:00:03.100] slot launch_slot_: id 0 | task 12 | processing task
[2026-08-10T14:00:03.100] n_past = 0
prompt eval time =    16900.00 ms /   74210 tokens (    0.23 ms per token,  4391.12 tokens per second)
       eval time =     1400.00 ms /     212 tokens (    6.60 ms per token,   151.43 tokens per second)
      total time =    18300.00 ms /   74422 tokens
"""


def test_parse_llama_server_log_extracts_prefill_and_decode():
    spans = parse_llama_server_log(SAMPLE_LOG)
    assert len(spans) == 1
    span = spans[0]
    assert span.prompt_tokens == 74210
    assert span.prompt_eval_ms == 16900.0
    assert span.eval_tokens == 212
    assert span.eval_ms == 1400.0
    assert span.slot_id == 0
    assert span.n_past == 0


def test_parse_llama_server_log_handles_multiple_requests():
    doubled = SAMPLE_LOG + "\n" + SAMPLE_LOG
    spans = parse_llama_server_log(doubled)
    assert len(spans) == 2


def test_correlate_and_store_matches_spans_to_assistant_messages(conn, settings):
    write_batch(conn, load_fixture_events(), settings)
    session_id = "ses_00fdbcb3affezdUs1su8KIvq3b"
    spans = parse_llama_server_log(SAMPLE_LOG)
    stored = correlate_and_store(conn, session_id, spans)
    assert stored == 1
    row = conn.execute("SELECT * FROM inference_spans WHERE session_id = ?", (session_id,)).fetchone()
    assert row["prompt_tokens"] == 74210
    assert 0 < row["match_confidence"] <= 1


def test_correlate_with_no_messages_stores_nothing(conn):
    spans = parse_llama_server_log(SAMPLE_LOG)
    stored = correlate_and_store(conn, "does-not-exist", spans)
    assert stored == 0
