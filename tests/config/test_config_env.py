import logging

import pytest

from aioscraper.config import load_config
from aioscraper.exceptions import ConfigValidationError


def test_load_config_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("SESSION_REQUEST_TIMEOUT", "5.5")
    monkeypatch.setenv("SESSION_SSL", "false")
    monkeypatch.setenv("SESSION_PROXY", "http://proxy:8080")

    monkeypatch.setenv("SCHEDULER_CONCURRENT_REQUESTS", "2")
    monkeypatch.setenv("SCHEDULER_PENDING_REQUESTS", "3")
    monkeypatch.setenv("SCHEDULER_CLOSE_TIMEOUT", "0.7")

    monkeypatch.setenv("EXECUTION_TIMEOUT", "1.2")
    monkeypatch.setenv("EXECUTION_SHUTDOWN_TIMEOUT", "0.4")
    monkeypatch.setenv("EXECUTION_SHUTDOWN_CHECK_INTERVAL", "0.05")
    monkeypatch.setenv("EXECUTION_LOG_LEVEL", "WARNING")

    monkeypatch.setenv("PIPELINE_STRICT", "false")

    config = load_config()

    assert config.session.timeout == 5.5
    assert config.session.ssl is False
    assert config.session.proxy == "http://proxy:8080"

    assert config.scheduler.concurrent_requests == 2
    assert config.scheduler.pending_requests == 3
    assert config.scheduler.close_timeout == 0.7

    assert config.execution.timeout == 1.2
    assert config.execution.shutdown_timeout == 0.4
    assert config.execution.shutdown_check_interval == 0.05
    assert config.execution.log_level == logging.WARNING

    assert config.pipeline.strict is False


def test_load_config_parses_proxy_json(monkeypatch):
    monkeypatch.setenv("SESSION_PROXY", '{"http": "http://p:1", "https": "http://p:2"}')

    config = load_config()

    assert config.session.proxy == {"http://": "http://p:1", "https://": "http://p:2"}


def test_load_config_raises_on_missing_scheduler_int(monkeypatch):
    monkeypatch.setenv("SCHEDULER_CONCURRENT_REQUESTS", "not-an-int")

    with pytest.raises((ValueError, ConfigValidationError)):
        load_config()


def test_load_config_raises_on_invalid_log_level(monkeypatch):
    monkeypatch.setenv("EXECUTION_LOG_LEVEL", "NOPE")

    with pytest.raises(ValueError):
        load_config()


def test_load_config_raises_on_invalid_proxy_url(monkeypatch):
    monkeypatch.setenv("SESSION_PROXY", "http://[::1")

    with pytest.raises(ExceptionGroup):
        load_config()
