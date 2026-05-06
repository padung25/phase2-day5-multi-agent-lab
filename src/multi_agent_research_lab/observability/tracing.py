"""Tracing hooks with local and optional LangSmith export."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from multi_agent_research_lab.core.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Create a local span and mirror it to LangSmith when configured.

    LangSmith export requires `LANGSMITH_API_KEY` plus the `langsmith` package. Local
    spans are always returned so tests and offline development still have traces.
    """

    settings = get_settings()
    started = perf_counter()
    start_time = datetime.now(UTC)
    span: dict[str, Any] = {
        "name": name,
        "attributes": attributes or {},
        "provider": "local",
        "duration_seconds": None,
    }
    run_id = None
    if settings.enable_remote_tracing:
        run_id = _create_langsmith_run(settings, name, attributes or {}, start_time)
    if run_id:
        span["provider"] = "langsmith"
        span["langsmith_run_id"] = str(run_id)

    error: str | None = None
    try:
        yield span
    except Exception as exc:
        error = repr(exc)
        span["error"] = error
        raise
    finally:
        duration = perf_counter() - started
        span["duration_seconds"] = duration
        if run_id:
            _finish_langsmith_run(settings, run_id, span, error)


@lru_cache(maxsize=1)
def _langsmith_client(api_key: str) -> Any | None:
    try:
        langsmith = importlib.import_module("langsmith")
    except ModuleNotFoundError:
        LOGGER.warning("LANGSMITH_API_KEY is set but the langsmith package is not installed")
        return None
    try:
        return langsmith.Client(api_key=api_key)
    except Exception:
        LOGGER.exception("Could not initialize LangSmith client")
        return None


def _create_langsmith_run(
    settings: Settings,
    name: str,
    attributes: dict[str, Any],
    start_time: datetime,
) -> UUID | None:
    if not settings.langsmith_api_key:
        return None
    client = _langsmith_client(settings.langsmith_api_key)
    if client is None:
        return None
    run_id = uuid4()
    try:
        client.create_run(
            id=run_id,
            name=name,
            run_type="chain",
            project_name=settings.langsmith_project,
            inputs={"attributes": attributes},
            start_time=start_time,
            extra={"metadata": attributes},
        )
    except Exception:
        LOGGER.exception("Could not create LangSmith run")
        return None
    return run_id


def _finish_langsmith_run(
    settings: Settings,
    run_id: UUID,
    span: dict[str, Any],
    error: str | None,
) -> None:
    if not settings.langsmith_api_key:
        return
    client = _langsmith_client(settings.langsmith_api_key)
    if client is None:
        return
    try:
        client.update_run(
            run_id,
            end_time=datetime.now(UTC),
            outputs={"span": span},
            error=error,
        )
        client.flush()
    except Exception:
        LOGGER.exception("Could not update LangSmith run")
