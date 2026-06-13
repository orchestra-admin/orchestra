import json
import logging

from orchestra_core.logging import JsonFormatter


def _make_record(
    msg: str, args: tuple = (), event: str | None = None
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=args,
        exc_info=None,
    )
    if event is not None:
        record.event = event
    return record


def test_json_formatter_substitutes_args_into_msg():
    """JsonFormatter applies record.args to record.msg via getMessage()."""
    record = _make_record("HTTP Request: %s %s", ("GET", "/foo"))
    out = json.loads(JsonFormatter().format(record))
    assert out["event"] == "HTTP Request: GET /foo"


def test_json_formatter_handles_msg_without_args():
    """JsonFormatter leaves a plain message unchanged when args is empty."""
    record = _make_record("plain message", ())
    out = json.loads(JsonFormatter().format(record))
    assert out["event"] == "plain message"


def test_json_formatter_prefers_extra_event_over_getmessage():
    """When extra={'event': ...} is set, that wins over record.getMessage()."""
    record = _make_record(
        "HTTP Request: %s", ("GET",), event="musician.job.completed"
    )
    out = json.loads(JsonFormatter().format(record))
    assert out["event"] == "musician.job.completed"
