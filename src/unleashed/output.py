"""Rendering. Table for humans, JSON for pipes, text for awk."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

import jmespath
from jmespath.exceptions import JMESPathError

from unleashed.errors import UsageError


class OutputFormat(StrEnum):
    TABLE = "table"
    JSON = "json"
    TEXT = "text"


def default_output(is_tty: bool) -> OutputFormat:
    """A terminal gets a table; a pipe gets JSON so scripts are not parsing columns."""
    return OutputFormat.TABLE if is_tty else OutputFormat.JSON


def apply_query(value: Any, query: str) -> Any:
    try:
        return jmespath.search(query, value)
    except JMESPathError as exc:
        raise UsageError(f"Invalid --query expression: {exc}") from exc


def render(value: Any, output: OutputFormat, query: str | None = None) -> str:
    if query:
        value = apply_query(value, query)
    if output is OutputFormat.JSON:
        return json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False)
    if output is OutputFormat.TEXT:
        return _as_text(value)
    return _as_table(value)


def _cell(value: Any) -> str:
    """A null field renders as an empty cell, never the word None."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _as_text(value: Any) -> str:
    """One record per line, one field per tab — the shape awk and cut expect."""
    if isinstance(value, list):
        return "\n".join(_row(item) for item in value)
    return _row(value)


def _row(value: Any) -> str:
    """A single line. A nested list is a row of cells, not a stack of lines."""
    if isinstance(value, dict):
        return "\t".join(_cell(v) for v in value.values())
    if isinstance(value, list):
        return "\t".join(_cell(v) for v in value)
    return _cell(value)


def _as_table(value: Any) -> str:
    if isinstance(value, list):
        return "\n\n".join(_as_table(item) for item in value)
    if not isinstance(value, dict):
        return _cell(value)
    width = max((len(k) for k in value), default=0)
    return "\n".join(f"{key.ljust(width)}  {_cell(val)}".rstrip() for key, val in value.items())
