from __future__ import annotations

import json

from viewer.detectors.base import SessionTrace
from viewer.detectors.repeated_tool_call import RepeatedToolCall
from viewer.detectors.tool_loop_alternating import ToolLoopAlternating
from viewer.detectors.no_prompt_cache import NoPromptCache
from viewer.detectors.time_unaccounted import TimeUnaccounted
from viewer.detectors.slow_tool import SlowTool
from viewer.detectors.oversized_output import OversizedOutput
from viewer.detectors.todo_stagnation import TodoStagnation
from viewer.detectors.cyrillic_identifier import CyrillicIdentifier
from viewer.detectors.tool_error import ToolError
from viewer.detectors.context_near_limit import ContextNearLimit


def _part(**kwargs):
    base = {
        "id": "p1", "type": "tool", "tool_name": "bash", "input_json": None, "output_text": None,
        "status": None, "duration_ms": None, "output_tokens_est": None, "error": None, "text": None,
        "seq": 0,
    }
    base.update(kwargs)
    return base


def _message(**kwargs):
    base = {
        "id": "m1", "seq": 0, "tokens_input": 0, "tokens_cache_read": 0,
    }
    base.update(kwargs)
    return base


def trace(session=None, messages=None, parts=None, todos=None):
    return SessionTrace(session=session or {}, messages=messages or [], parts=parts or [], todo_snapshots=todos or [])


def test_repeated_tool_call_fires_on_three_equivalent_calls_but_not_two():
    same_sql = json.dumps({"command": "select * from t where x='1'"})
    other_sql = json.dumps({"command": "select * from t where x='2'"})

    three = trace(parts=[_part(id=str(i), input_json=same_sql) for i in range(3)])
    assert RepeatedToolCall().run(three)

    two = trace(parts=[_part(id=str(i), input_json=same_sql) for i in range(2)])
    assert not RepeatedToolCall().run(two)

    # reformatted-but-equivalent SQL (different literal, spacing) must still match
    reformatted = [
        _part(id="a", input_json=json.dumps({"command": "SELECT * FROM t WHERE x = '1'"})),
        _part(id="b", input_json=json.dumps({"command": "select   *   from t where x='99'"})),
        _part(id="c", input_json=json.dumps({"command": "select * from t where x='7' -- note"})),
    ]
    assert RepeatedToolCall().run(trace(parts=reformatted))

    unrelated = trace(parts=[_part(id="x", input_json=other_sql), _part(id="y", input_json=same_sql)])
    assert not RepeatedToolCall().run(unrelated)


def test_tool_loop_alternating():
    sig_a = json.dumps({"command": "a"})
    sig_b = json.dumps({"command": "b"})
    alternating = trace(parts=[_part(id=str(i), input_json=(sig_a if i % 2 == 0 else sig_b), seq=i) for i in range(8)])
    assert ToolLoopAlternating().run(alternating)

    not_looping = trace(parts=[_part(id=str(i), input_json=sig_a, seq=i) for i in range(3)])
    assert not ToolLoopAlternating().run(not_looping)


def test_no_prompt_cache():
    bad = trace(session={}, messages=[_message(tokens_input=60_000, tokens_cache_read=0)])
    assert NoPromptCache().run(bad)

    ok_cache = trace(messages=[_message(tokens_input=60_000, tokens_cache_read=40_000)])
    assert not NoPromptCache().run(ok_cache)

    small = trace(messages=[_message(tokens_input=1000, tokens_cache_read=0)])
    assert not NoPromptCache().run(small)


def test_time_unaccounted():
    bad = trace(session={"duration_ms": 100_000, "unaccounted_ms": 60_000})
    assert TimeUnaccounted().run(bad)

    ok = trace(session={"duration_ms": 100_000, "unaccounted_ms": 10_000})
    assert not TimeUnaccounted().run(ok)


def test_slow_tool():
    slow = trace(parts=[_part(id="1", duration_ms=15_000)])
    assert SlowTool().run(slow)

    fast = trace(parts=[_part(id="1", duration_ms=500)])
    assert not SlowTool().run(fast)


def test_oversized_output():
    big = trace(parts=[_part(id="1", output_tokens_est=25_000)])
    assert OversizedOutput().run(big)

    small = trace(parts=[_part(id="1", output_tokens_est=100)])
    assert not OversizedOutput().run(small)


def test_todo_stagnation_and_missing_ids():
    stagnant = trace(todos=[{"items_json": json.dumps([
        {"content": "a", "status": "pending", "priority": "low"},
        {"content": "b", "status": "pending", "priority": "low"},
    ])}])
    results = TodoStagnation().run(stagnant)
    kinds = {r.message for r in results}
    assert any("не закрыт ни один" in m for m in kinds)
    assert any("нет стабильного id" in m for m in kinds)

    progressed = trace(todos=[{"items_json": json.dumps([
        {"content": "a", "status": "completed", "priority": "low", "id": "1"},
        {"content": "b", "status": "pending", "priority": "low", "id": "2"},
    ])}])
    results2 = TodoStagnation().run(progressed)
    assert not any("не закрыт ни один" in r.message for r in results2)
    assert not any("нет стабильного id" in r.message for r in results2)


def test_cyrillic_identifier():
    bad = trace(parts=[_part(id="1", input_json=json.dumps({"command": "select * from [Клиенты]"}, ensure_ascii=False))])
    assert CyrillicIdentifier().run(bad)

    bad2 = trace(parts=[_part(id="1", input_json=json.dumps({"command": "select * from Клиенты"}, ensure_ascii=False))])
    assert CyrillicIdentifier().run(bad2)

    ok = trace(parts=[_part(id="1", input_json=json.dumps({"command": "select * from customers"}))])
    assert not CyrillicIdentifier().run(ok)


def test_tool_error():
    failed = trace(parts=[_part(id="1", status="error", error="boom")])
    assert ToolError().run(failed)

    ok = trace(parts=[_part(id="1", status="completed")])
    assert not ToolError().run(ok)


def test_context_near_limit():
    near = trace(session={"model": "qwen2.5-coder-32b"}, messages=[_message(tokens_input=110_000, seq=1, id="m1")])
    assert ContextNearLimit().run(near)

    fine = trace(session={"model": "qwen2.5-coder-32b"}, messages=[_message(tokens_input=1000, seq=1, id="m1")])
    assert not ContextNearLimit().run(fine)

    unknown_model = trace(session={"model": "some-unknown-model"}, messages=[_message(tokens_input=999_999, seq=1, id="m1")])
    assert not ContextNearLimit().run(unknown_model)
