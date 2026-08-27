"""Turning an exception into what the user sees and what the shell gets back."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import click

from unleashed.errors import UnleashedError, ValidationError

F = TypeVar("F", bound=Callable[..., Any])


def report(error: UnleashedError) -> None:
    click.echo(f"Error: {error}", err=True)
    if isinstance(error, ValidationError):
        for field, messages in error.errors.items():
            for message in messages:
                click.echo(f"  {field}: {message}", err=True)


def handle_errors(func: F) -> F:
    """Report a deliberate error and exit with its code, rather than a traceback."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except UnleashedError as error:
            report(error)
            click.get_current_context().exit(int(error.exit_code))

    return wrapper  # type: ignore[return-value]
