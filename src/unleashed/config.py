"""Credential resolution.

Three layers, lowest precedence first:

    environment variables       UNLEASHED_API_URL / UNLEASHED_API_TOKEN
    home config                 ~/.unleashed/config
    local config                the nearest .unleashed/config at or above the
                                working directory, stopping before the home one

Layers merge per key, so a local file carrying only a token inherits the URL from
home. That is what makes several accounts on one machine practical: one home config
with the URL and a personal token, and a per-project file that swaps the token.

Environment variables sit at the bottom deliberately. A stale export in a shell must
not quietly hijack a project directory that has said which account it belongs to.

Within a file only the named profile section is read. A profile does not inherit from
[default] — an account half-described in two sections is worse than a clear error.
"""

from __future__ import annotations

import configparser
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from unleashed.errors import ConfigError

CONFIG_DIR_NAME = ".unleashed"
CONFIG_FILE_NAME = "config"
DEFAULT_PROFILE = "default"

URL_KEY = "api_url"
TOKEN_KEY = "api_token"

URL_VAR = "UNLEASHED_API_URL"
TOKEN_VAR = "UNLEASHED_API_TOKEN"
PROFILE_VAR = "UNLEASHED_PROFILE"

REDACTED = "Bearer ***redacted***"

#: Any bit set here means someone other than the owner can read the token.
_EXPOSED = stat.S_IRWXG | stat.S_IRWXO


@dataclass(frozen=True)
class Config:
    base_url: str
    token: str
    profile: str = DEFAULT_PROFILE
    sources: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __repr__(self) -> str:
        """Never let the token reach a traceback or a log line."""
        return f"Config(base_url={self.base_url!r}, profile={self.profile!r}, token=***redacted***)"

    def headers(self, *, redact: bool = False) -> dict[str, str]:
        return {
            "Authorization": REDACTED if redact else f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }


def config_path_in(directory: Path) -> Path:
    return directory / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def home_config_path(home: Path | None = None) -> Path:
    return config_path_in(home if home is not None else Path.home())


def find_local_config(start: Path, home: Path) -> Path | None:
    """The nearest .unleashed/config at or above `start`, ignoring the home one.

    Walking up means a script in a subdirectory still resolves to the account its
    project declared. The home config is skipped here so it is never counted twice.
    """
    home = home.resolve()
    for directory in (start.resolve(), *start.resolve().parents):
        if directory == home:
            break
        candidate = config_path_in(directory)
        if candidate.is_file():
            return candidate
    return None


def _parser() -> configparser.ConfigParser:
    """Interpolation off: a token is an opaque string and may contain a percent sign."""
    return configparser.ConfigParser(interpolation=None)


def _parse(path: Path) -> configparser.ConfigParser:
    parser = _parser()
    try:
        parser.read_string(path.read_text(), source=str(path))
    except (configparser.Error, OSError) as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc
    return parser


def _values_for(parser: configparser.ConfigParser, profile: str) -> dict[str, str]:
    if not parser.has_section(profile):
        return {}
    return {key: value.strip() for key, value in parser.items(profile) if value.strip()}


def _permission_warning(path: Path) -> str | None:
    if path.stat().st_mode & _EXPOSED:
        return f"{path} is readable by other users. It holds an API token — run: chmod 600 {path}"
    return None


def _known_profiles(parsers: list[tuple[Path, configparser.ConfigParser]]) -> list[str]:
    seen: list[str] = []
    for _path, parser in parsers:
        seen.extend(section for section in parser.sections() if section not in seen)
    return seen


def _missing_error(key: str, env_var: str, paths: list[Path], profile: str) -> ConfigError:
    if paths:
        where = "\n".join(f"  {path}" for path in paths)
        return ConfigError(
            f"No {key} found for profile '{profile}'. Looked in:\n{where}\n"
            f"Set it there, export {env_var}, or run: unleashed configure"
        )
    return ConfigError(
        f"No {key} found. There is no {CONFIG_DIR_NAME}/{CONFIG_FILE_NAME} to read.\n"
        f"Run: unleashed configure\n"
        f"Or export {env_var}."
    )


def load_config(
    env: Mapping[str, str],
    *,
    profile: str | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> Config:
    """Resolve credentials, or fail with a message naming every place we looked."""
    home = home if home is not None else Path.home()
    cwd = cwd if cwd is not None else Path.cwd()
    resolved_profile = profile or env.get(PROFILE_VAR, "").strip() or DEFAULT_PROFILE

    candidates = [path for path in (home_config_path(home), find_local_config(cwd, home)) if path]
    present = [path for path in candidates if path.is_file()]

    parsers = [(path, _parse(path)) for path in present]
    warnings = tuple(w for path in present if (w := _permission_warning(path)))

    # Lowest precedence first: env, then home, then local.
    values: dict[str, str] = {
        key: value
        for key, value in (
            (URL_KEY, env.get(URL_VAR, "").strip()),
            (TOKEN_KEY, env.get(TOKEN_VAR, "").strip()),
        )
        if value
    }
    sources: list[str] = []
    for path, parser in parsers:
        layer = _values_for(parser, resolved_profile)
        if layer:
            values.update(layer)
            sources.append(str(path))

    if not sources and present and resolved_profile != DEFAULT_PROFILE:
        known = _known_profiles(parsers)
        available = ", ".join(known) if known else "none"
        raise ConfigError(f"No profile named '{resolved_profile}'. Profiles found: {available}")

    url = values.get(URL_KEY, "")
    token = values.get(TOKEN_KEY, "")
    if not url:
        raise _missing_error(URL_KEY, URL_VAR, present, resolved_profile)
    if not token:
        raise _missing_error(TOKEN_KEY, TOKEN_VAR, present, resolved_profile)

    return Config(
        base_url=url.rstrip("/"),
        token=token,
        profile=resolved_profile,
        sources=tuple(sources),
        warnings=warnings,
    )


def write_config(path: Path, profile: str, url: str, token: str) -> None:
    """Create or update one profile, leaving every other profile untouched."""
    parser = _parser()
    if path.is_file():
        parser = _parse(path)
    if not parser.has_section(profile):
        parser.add_section(profile)
    parser.set(profile, URL_KEY, url)
    parser.set(profile, TOKEN_KEY, token)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    # Create with owner-only permissions before any token is written to disk.
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    with path.open("w") as handle:
        parser.write(handle)


def read_existing(path: Path, profile: str) -> dict[str, str]:
    """Current values for a profile, so `configure` can offer them as defaults."""
    if not path.is_file():
        return {}
    return _values_for(_parse(path), profile)
