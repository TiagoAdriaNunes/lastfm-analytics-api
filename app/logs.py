"""App logging with loguru, written to stdout (Railway collects it).

Log with `from loguru import logger` and pass fields as keyword arguments:
`logger.info("GET {path} -> {status}", path=path, status=200)`. They fill the message and also
become top-level fields in the JSON output. Keep the message template a constant: user input goes
in the keyword arguments, never in the template.

Uvicorn's loggers are routed into loguru so everything shares one format. The root logger is
deliberately left alone: httpx(2) logs every request URL at INFO, and Last.fm URLs carry our
`api_key` in the query string."""

import json
import logging
import sys
import traceback
from contextlib import suppress
from typing import TYPE_CHECKING, Literal

from loguru import logger

if TYPE_CHECKING:
    from loguru import Message

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["text", "json"]

# Stdlib loggers routed into loguru. Only these: see the module docstring about httpx.
# ("uvicorn.error" has no handler of its own and propagates to "uvicorn".)
INTERCEPTED_LOGGERS = ("uvicorn",)
# Uvicorn's access log, silenced: our request middleware logs each request with its duration.
# Uvicorn only writes access lines while this logger has handlers, so emptying it switches them
# off without needing `--no-access-log` in every start command.
SILENCED_LOGGERS = ("uvicorn.access",)

TEXT_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}: {message}"


class InterceptHandler(logging.Handler):
    """Forward stdlib log records to loguru, keeping the stdlib logger's name (e.g.
    `uvicorn.error`) as the record's `name`."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.patch(
            lambda r: r.update(name=record.name, function=record.funcName, line=record.lineno)
        ).opt(exception=record.exc_info).log(level, record.getMessage())


def _write_json(message: "Message") -> None:
    """One flat JSON object per line, so Railway turns the fields into filters
    (e.g. `@status:502` or `@lastfm_method:artist.getInfo`). Loguru's own `serialize=True`
    nests them under `record.extra`."""
    record = message.record
    entry = {
        "time": record["time"].isoformat(timespec="milliseconds"),
        "level": record["level"].name.lower(),
        "logger": record["name"],
        "message": record["message"],
        **record["extra"],
    }
    if (exc := record["exception"]) is not None:
        entry["exception"] = "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))
    _write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")


def _write_text(message: "Message") -> None:
    _write(message)


def _write(line: str) -> None:
    # sys.stdout looked up on every write: test runners swap it out. Flushed every line: when
    # stdout is a pipe (Railway, Docker) Python buffers it, delaying logs and losing the last
    # ones if the process dies.
    sys.stdout.write(line)
    sys.stdout.flush()


_handler_id: int | None = None


def setup_logging(level: LogLevel, fmt: LogFormat) -> None:
    """Called when `app.main` is imported, so even uvicorn's first lines use our format.
    Idempotent and only replaces our own sink, so sinks added elsewhere (e.g. by tests) survive."""
    global _handler_id
    if _handler_id is None:
        with suppress(ValueError):
            logger.remove(0)  # loguru's default stderr sink
    else:
        logger.remove(_handler_id)
    _handler_id = logger.add(
        _write_json if fmt == "json" else _write_text,
        level=level,
        format=TEXT_FORMAT,  # ignored by the JSON sink, which builds its own line
        # Never print local variables in tracebacks: they can hold the API keys.
        backtrace=False,
        diagnose=False,
    )

    # Uvicorn configures its loggers before importing the app, so this runs after and wins.
    for name in INTERCEPTED_LOGGERS:
        std_logger = logging.getLogger(name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False
    logging.getLogger("uvicorn.error").handlers = []
    logging.getLogger("uvicorn.error").propagate = True
    for name in SILENCED_LOGGERS:
        std_logger = logging.getLogger(name)
        std_logger.handlers = []
        std_logger.propagate = False
