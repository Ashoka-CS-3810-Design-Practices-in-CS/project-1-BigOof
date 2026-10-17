import logging

import pytest

import big_o.app as metro_app
from big_o import logging_config


@pytest.fixture
def client():
    metro_app.app.config.update(TESTING=True)
    with metro_app.app.test_client() as test_client:
        yield test_client


def messages(caplog, level=None):
    return [r.getMessage() for r in caplog.records if r.name == "big_o" and (level is None or r.levelno == level)]


def test_every_request_is_logged_with_a_request_id(client, caplog):
    with caplog.at_level(logging.INFO, logger="big_o"):
        response = client.get("/health")

    request_id = response.headers["X-Request-ID"]
    assert request_id
    assert any(m.startswith("GET /health -> 200") and f"[req {request_id}]" in m for m in messages(caplog))


def test_safe_incoming_request_id_is_reused(client):
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})

    assert response.headers["X-Request-ID"] == "abc-123"


def test_unsafe_incoming_request_id_is_replaced(client):
    response = client.get("/health", headers={"X-Request-ID": "x" * 65})

    assert response.headers["X-Request-ID"] != "x" * 65


def test_error_responses_log_a_warning_with_the_error_code(client, caplog):
    with caplog.at_level(logging.INFO, logger="big_o"):
        client.post("/route", json={"source": "A", "dest": "D", "mode": "cheapest"})

    warnings = messages(caplog, logging.WARNING)
    assert any("POST /route -> 400" in m and "error=invalid_mode" in m for m in warnings)


def test_successful_route_is_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="big_o"):
        client.post("/route", json={"source": "50", "dest": "92", "mode": "fastest"})

    assert any(m.startswith("Route 50 -> 92 mode=fastest via=0") for m in messages(caplog))


def test_unexpected_errors_are_logged_with_traceback(client, caplog, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(metro_app.metro_graph, "fastestRoute", explode)
    with caplog.at_level(logging.INFO, logger="big_o"):
        response = client.post("/route", json={"source": "50", "dest": "92", "mode": "fastest"})

    assert response.status_code == 500
    assert response.get_json()["error"] == "internal_error"
    errors = [r for r in caplog.records if r.name == "big_o" and r.levelno == logging.ERROR]
    assert any(r.exc_info and "Unhandled error on POST /route" in r.getMessage() for r in errors)


def test_missing_page_is_a_normal_404(client):
    assert client.get("/does-not-exist").status_code == 404


def test_ui_event_is_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="big_o"):
        response = client.post("/log", json={"event": "mode_changed", "details": {"mode": "fastest"}})

    assert response.status_code == 204
    assert any(m.startswith('UI mode_changed {"mode": "fastest"}') for m in messages(caplog))


def test_ui_event_text_cannot_break_onto_a_new_log_line(client, caplog):
    with caplog.at_level(logging.INFO, logger="big_o"):
        client.post("/log", json={"event": "js_error", "details": {"message": "x\nFAKE ERROR line"}})

    (line,) = [m for m in messages(caplog) if m.startswith("UI js_error")]
    assert "\n" not in line


@pytest.mark.parametrize(
    "payload",
    [
        "not an object",
        {},
        {"event": "made_up_event"},
        {"event": "mode_changed", "details": "fastest"},
        {"event": "mode_changed", "details": {"nested": {"a": 1}}},
        {"event": "mode_changed", "details": {"long": "x" * 201}},
        {"event": "mode_changed", "details": {f"k{i}": i for i in range(11)}},
    ],
)
def test_invalid_ui_events_are_rejected(client, payload):
    response = client.post("/log", json=payload)

    assert response.status_code == 400


def make_logger(monkeypatch, tmp_path, **env):
    # A fresh, unconfigured logger so configure_logging runs from scratch.
    monkeypatch.setattr(logging_config, "LOGGER_NAME", f"big_o_test_{tmp_path.name}")
    for key in ("LOG_DIR", "VERCEL", "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    logger = logging_config.configure_logging()
    return logger, list(logger.handlers)


def test_logs_are_written_to_a_file_locally(monkeypatch, tmp_path):
    log_dir = tmp_path / ".logs"
    logger, handlers = make_logger(monkeypatch, tmp_path, LOG_DIR=str(log_dir))

    logger.info("hello file")
    for handler in handlers:
        handler.flush()

    assert "hello file" in (log_dir / "big_o.log").read_text()
    for handler in handlers:
        handler.close()


def test_no_log_file_on_vercel(monkeypatch, tmp_path):
    log_dir = tmp_path / ".logs"
    _, handlers = make_logger(monkeypatch, tmp_path, LOG_DIR=str(log_dir), VERCEL="1")

    assert len(handlers) == 1  # stdout only
    assert not log_dir.exists()


def test_unwritable_log_dir_falls_back_to_stdout(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    _, handlers = make_logger(monkeypatch, tmp_path, LOG_DIR=str(blocker / "logs"))

    assert len(handlers) == 1


def test_configure_logging_is_idempotent(monkeypatch, tmp_path):
    logger, handlers = make_logger(monkeypatch, tmp_path, LOG_DIR="")

    assert logging_config.configure_logging() is logger
    assert len(logger.handlers) == len(handlers) == 1


def test_log_level_from_environment(monkeypatch, tmp_path):
    logger, _ = make_logger(monkeypatch, tmp_path, LOG_DIR="", LOG_LEVEL="debug")

    assert logger.level == logging.DEBUG
