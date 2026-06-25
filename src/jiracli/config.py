"""Typed configuration for jiracli.

Non-secret settings (Jira URL, poll interval) live in a validated ``config.toml``
loaded through pydantic-settings. The Personal Access Token is a secret and is
*not* stored in that file: it is read from the OS keyring, falling back to the
``JIRA_PAT`` environment variable.
"""

from __future__ import annotations

import tomllib
from typing import Type

import keyring
import tomli_w
from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from jiracli.paths import config_file

KEYRING_SERVICE = "jiracli"
KEYRING_USERNAME = "pat"
PAT_ENV_VAR = "JIRA_PAT"

DEFAULT_URL = "https://its.cern.ch/jira"


class Settings(BaseSettings):
    """Validated jiracli settings, sourced from ``config.toml`` + environment.

    Environment variables (prefix ``JIRACLI_``, e.g. ``JIRACLI_POLL_SECONDS``)
    override values from the TOML file.
    """

    model_config = SettingsConfigDict(
        env_prefix="JIRACLI_",
        extra="ignore",
    )

    url: str = Field(default=DEFAULT_URL, description="Base URL of the Jira instance")
    poll_seconds: int = Field(
        default=60, ge=10, description="Background poll interval in seconds"
    )

    @field_validator("url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: explicit init args > environment > config.toml.
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=config_file()),
        )


def load_settings() -> Settings:
    """Load and validate settings. Raises on malformed config."""
    return Settings()


def save_settings(url: str, poll_seconds: int) -> None:
    """Write the non-secret settings to ``config.toml`` and re-validate."""
    url = url.rstrip("/")
    path = config_file()
    data: dict[str, object] = {}
    if path.exists():
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    data["url"] = url
    data["poll_seconds"] = poll_seconds
    with path.open("wb") as fh:
        tomli_w.dump(data, fh)
    # Re-validate by constructing Settings (raises if the file is now invalid).
    load_settings()


# --- PAT (secret) handling -------------------------------------------------


def get_token() -> str | None:
    """Resolve the PAT: keyring first, then ``JIRA_PAT`` env var."""
    import os

    token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if token:
        return token
    return os.environ.get(PAT_ENV_VAR)


def save_token(token: str) -> None:
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)


def require_token() -> str:
    token = get_token()
    if not token:
        raise RuntimeError(
            "No Jira token found. Run `jiracli configure` to store one, "
            f"or set the {PAT_ENV_VAR} environment variable."
        )
    return token
