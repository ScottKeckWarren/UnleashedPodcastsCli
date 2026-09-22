"""Turning an exception into what the user sees and what the shell gets back."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import click

from unleashed.errors import AuthError, ForbiddenError, UnleashedError, ValidationError

F = TypeVar("F", bound=Callable[..., Any])


#: What to do next, for the failures a fresh token fixes.
HINTS: dict[type[UnleashedError], str] = {
    AuthError: "Run: unleashed login",
    ForbiddenError: (
        "This token does not grant that action. Run: unleashed login, "
        "and approve the ability it needs."
    ),
}


def report(error: UnleashedError) -> None:
    click.echo(f"Error: {error}", err=True)
    hint = HINTS.get(type(error))
    if hint:
        click.echo(hint, err=True)
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
