"""Machine-local configuration and safe probing for summary model endpoints.

The web setup page needs to be able to help a user connect an already-running
OpenAI-compatible model server without being given permission to execute a
command or rewrite the archive credentials.  This module keeps that seam small:

* the runtime configuration is a credential-free JSON file in ``.chatreview``;
* environment variables remain the fallback for existing installations;
* probing performs one bounded ``GET /models`` request and follows no redirects;
* response data is reduced to model identifiers before it crosses the API.

The probe deliberately permits loopback, private, and Tailscale addresses because
those are the supported locations for a self-hosted model.  It rejects
unspecified, link-local, multicast, and reserved destinations, including cloud
metadata addresses.  Public HTTPS endpoints are also supported for users who
already have a hosted OpenAI-compatible service.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SUMMARY_PROVIDER_RUNTIME_FILE = "summary-provider.json"
CANONICAL_PROVIDER = "openai-compatible"
OPENAI_COMPATIBLE_PROVIDERS = frozenset({"openai", "openai-compatible", "qwen", "local"})
SUMMARY_PROVIDER_CONFIGURATION_KEYS = (
    "provider",
    "model",
    "base_url",
    "disable_thinking",
    "updated_at",
)
MAX_BASE_URL_LENGTH = 2_048
MAX_MODEL_LENGTH = 512
MAX_PROBE_RESPONSE_BYTES = 1_048_576
DEFAULT_PROBE_TIMEOUT = 5.0


class SummaryConfigurationError(ValueError):
    """Raised when a summary provider configuration is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class SummaryProviderConfiguration:
    """Credential-free summary endpoint configuration."""

    provider: str
    model: str | None
    base_url: str | None
    disable_thinking: bool
    source: str
    updated_at: str | None = None

    @property
    def configured(self) -> bool:
        """Whether this contains enough information for an OpenAI-compatible provider."""

        return (
            self.provider in OPENAI_COMPATIBLE_PROVIDERS
            and bool(self.model)
            and bool(self.base_url)
        )

    def to_public_dict(self, *, api_key_configured: bool = False) -> dict[str, Any]:
        """Return only values safe for the setup API response."""

        return {
            "configured": self.configured,
            "provider": _public_text(self.provider, limit=80),
            "model": _public_text(self.model, limit=MAX_MODEL_LENGTH),
            "base_url": self.base_url,
            "disable_thinking": self.disable_thinking,
            "source": self.source,
            "updated_at": self.updated_at,
            "api_key_configured": api_key_configured,
            "runtime_file": SUMMARY_PROVIDER_RUNTIME_FILE,
        }


@dataclass(frozen=True, slots=True)
class SummaryProbeResult:
    """Credential-free result of one model-list probe."""

    ok: bool
    stage: str
    message: str
    base_url: str | None
    models: tuple[str, ...] = ()
    selected_model: str | None = None
    model_available: bool | None = None
    checks: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the staged result for FastAPI."""

        return {
            "ok": self.ok,
            "stage": self.stage,
            "message": self.message,
            "base_url": self.base_url,
            "models": list(self.models),
            "selected_model": self.selected_model,
            "model_available": self.model_available,
            "checks": [dict(check) for check in self.checks],
        }


def normalize_provider(value: str) -> str:
    """Normalize supported local/provider aliases to the persisted provider id."""

    provider = _validated_text(value, field="provider", limit=80).lower()
    if provider not in OPENAI_COMPATIBLE_PROVIDERS:
        raise SummaryConfigurationError(
            "summary setup supports the openai-compatible provider (including qwen/local aliases)"
        )
    return CANONICAL_PROVIDER


def validate_model(value: str) -> str:
    """Validate a model identifier before it is persisted or sent to a provider."""

    return _validated_text(value, field="model", limit=MAX_MODEL_LENGTH)


def normalize_base_url(value: str) -> str:
    """Validate and normalize an HTTP(S) provider base URL.

    Credentials, query strings, fragments, control characters, and malformed
    ports are rejected so a URL cannot smuggle a secret into the runtime file or
    the probe request.  The endpoint path is retained (normally ``/v1``).
    """

    if not isinstance(value, str):
        raise SummaryConfigurationError("summary provider base URL must be a string")
    candidate = value.strip().rstrip("/")
    if not candidate:
        raise SummaryConfigurationError("summary provider base URL is required")
    if len(candidate) > MAX_BASE_URL_LENGTH:
        raise SummaryConfigurationError("summary provider base URL is too long")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in candidate):
        raise SummaryConfigurationError("summary provider base URL must not contain control characters")
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        # Accessing .port validates malformed and out-of-range ports.
        port = parsed.port
    except ValueError as exc:
        raise SummaryConfigurationError("summary provider base URL has an invalid host or port") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
        raise SummaryConfigurationError("summary provider base URL must use http or https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SummaryConfigurationError(
            "summary provider base URL must not contain credentials, query data, or a fragment"
        )
    if any(character.isspace() for character in candidate):
        raise SummaryConfigurationError("summary provider base URL must not contain whitespace")
    if port == 0:
        raise SummaryConfigurationError("summary provider base URL must use a valid port")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            parsed.path.rstrip("/"),
            "",
            "",
        )
    )


def runtime_configuration_path(data_dir: Path) -> Path:
    """Return the private, machine-local runtime configuration path."""

    return Path(data_dir).expanduser() / SUMMARY_PROVIDER_RUNTIME_FILE


def setup_actions_enabled(
    client_host: str | None,
    *,
    remote_env: str = "CHATREVIEW_ALLOW_REMOTE_SUMMARY_SETUP",
) -> bool:
    """Return whether a request may mutate machine-local setup state.

    Setup actions are local-only by default.  A caller supplies the explicit
    opt-in environment variable for its feature.  Proxy headers are
    deliberately ignored; trusting an unverified ``X-Forwarded-For`` would
    defeat this guard.
    """

    try:
        address = ipaddress.ip_address(client_host or "")
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address.is_loopback:
        return True
    if not _env_bool(remote_env):
        return False
    return address.is_private or _is_tailscale_address(address)


def load_runtime_configuration(data_dir: Path) -> SummaryProviderConfiguration | None:
    """Load the runtime provider file, returning ``None`` when it is absent."""

    path = runtime_configuration_path(data_dir)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise SummaryConfigurationError("summary provider runtime file is not a regular file")
    if not _owned_by_current_user(path):
        raise SummaryConfigurationError("summary provider runtime file is not owned by this user")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SummaryConfigurationError("summary provider runtime file could not be read") from exc
    except json.JSONDecodeError as exc:
        raise SummaryConfigurationError("summary provider runtime file contains invalid JSON") from exc
    if not isinstance(payload, dict):
        raise SummaryConfigurationError("summary provider runtime file must contain one JSON object")
    unknown_keys = set(payload) - set(SUMMARY_PROVIDER_CONFIGURATION_KEYS)
    if unknown_keys:
        raise SummaryConfigurationError("summary provider runtime file contains unknown keys")
    try:
        provider = normalize_provider(str(payload["provider"]))
        model = validate_model(payload["model"])
        base_url = normalize_base_url(payload["base_url"])
    except KeyError as exc:
        raise SummaryConfigurationError(
            f"summary provider runtime file is missing {exc.args[0]}"
        ) from exc
    disable_thinking = payload.get("disable_thinking", False)
    if not isinstance(disable_thinking, bool):
        raise SummaryConfigurationError("disable_thinking must be true or false")
    updated_at = payload.get("updated_at")
    if updated_at is not None and not isinstance(updated_at, str):
        raise SummaryConfigurationError("updated_at must be a string")
    return SummaryProviderConfiguration(
        provider=provider,
        model=model,
        base_url=base_url,
        disable_thinking=disable_thinking,
        source="runtime",
        updated_at=updated_at,
    )


def current_configuration(data_dir: Path) -> SummaryProviderConfiguration | None:
    """Return runtime configuration first, with environment compatibility fallback."""

    runtime = load_runtime_configuration(data_dir)
    if runtime is not None:
        return runtime

    raw_provider = os.environ.get("CHATREVIEW_SUMMARY_PROVIDER", "").strip().lower()
    if not raw_provider:
        return None
    provider = (
        normalize_provider(raw_provider)
        if raw_provider in OPENAI_COMPATIBLE_PROVIDERS
        else _public_text(raw_provider, limit=80)
    )
    raw_model = os.environ.get("CHATREVIEW_SUMMARY_MODEL", "").strip()
    model = _safe_optional_model(raw_model)
    raw_url = os.environ.get("CHATREVIEW_SUMMARY_BASE_URL", "").strip()
    base_url = None
    if raw_url:
        try:
            base_url = normalize_base_url(raw_url)
        except SummaryConfigurationError:
            # Keep status readable while the probe/configuration endpoint explains
            # the exact correction; never echo an unsafe environment value.
            base_url = None
    return SummaryProviderConfiguration(
        provider=provider,
        model=model,
        base_url=base_url,
        disable_thinking=_env_bool("CHATREVIEW_SUMMARY_DISABLE_THINKING"),
        source="environment",
    )


def save_runtime_configuration(
    data_dir: Path,
    *,
    provider: str,
    model: str,
    base_url: str,
    disable_thinking: bool,
) -> SummaryProviderConfiguration:
    """Atomically save an allowlisted, credential-free runtime configuration."""

    if not isinstance(disable_thinking, bool):
        raise SummaryConfigurationError("disable_thinking must be true or false")
    configuration = SummaryProviderConfiguration(
        provider=normalize_provider(provider),
        model=validate_model(model),
        base_url=normalize_base_url(base_url),
        disable_thinking=disable_thinking,
        source="runtime",
        updated_at=_now(),
    )
    path = runtime_configuration_path(data_dir)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.parent.chmod(0o700)
    except OSError as exc:
        raise SummaryConfigurationError(
            "summary provider runtime directory could not be secured"
        ) from exc
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SummaryConfigurationError("summary provider runtime file is not a regular file")
    if path.exists() and not _owned_by_current_user(path):
        raise SummaryConfigurationError("summary provider runtime file is not owned by this user")
    payload = {
        "provider": configuration.provider,
        "model": configuration.model,
        "base_url": configuration.base_url,
        "disable_thinking": configuration.disable_thinking,
        "updated_at": configuration.updated_at,
    }
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    except OSError as exc:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        raise SummaryConfigurationError("summary provider runtime configuration could not be saved") from exc
    return configuration


def probe_openai_compatible(
    base_url: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> SummaryProbeResult:
    """Probe one endpoint's ``/models`` resource with staged safe feedback.

    ``api_key`` is intentionally an ephemeral argument.  The API layer may accept
    one from an explicit user action for a hosted service, but this module never
    persists it or includes it in a result.  Callers should omit it for local
    servers and may source it from an existing trusted configuration for a known
    endpoint.
    """

    checks: list[dict[str, str]] = []
    try:
        normalized_url = normalize_base_url(base_url)
    except SummaryConfigurationError as exc:
        return _probe_failure("validate", str(exc), None, checks)
    checks.append({"id": "url", "status": "passed", "message": "The endpoint URL is valid"})
    selected_model: str | None = None
    if model is not None and model.strip():
        try:
            selected_model = validate_model(model)
        except SummaryConfigurationError as exc:
            return _probe_failure("validate", str(exc), normalized_url, checks)

    parsed = urlsplit(normalized_url)
    try:
        _check_resolved_addresses(
            parsed.hostname or "",
            parsed.port or (443 if parsed.scheme == "https" else 80),
            scheme=parsed.scheme,
        )
    except _ProbeFailure as failure:
        return _probe_failure(failure.stage, failure.message, normalized_url, checks)
    checks.append({"id": "network", "status": "passed", "message": "The destination is allowed"})

    endpoint = f"{normalized_url}/models"
    request_headers = {"Accept": "application/json"}
    if api_key:
        request_headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(endpoint, headers=request_headers, method="GET")
    try:
        response = _open_without_redirects(request, timeout=max(0.1, min(float(timeout), 15.0)))
        with response:
            status_value = getattr(response, "status", None)
            status = int(status_value if status_value is not None else response.getcode())
            if status < 200 or status >= 300:
                return _probe_failure(
                    "connect",
                    _http_message(status),
                    normalized_url,
                    checks,
                )
            raw = response.read(MAX_PROBE_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            message = "The endpoint redirected the probe; redirects are disabled for safety"
        else:
            message = _http_message(exc.code)
        return _probe_failure("connect", message, normalized_url, checks)
    except (urllib.error.URLError, TimeoutError, OSError):
        return _probe_failure(
            "connect",
            "The endpoint could not be reached; check the host, port, and network connection",
            normalized_url,
            checks,
        )
    if len(raw) > MAX_PROBE_RESPONSE_BYTES:
        return _probe_failure(
            "response",
            "The /models response is larger than the safe probe limit",
            normalized_url,
            checks,
        )
    checks.append({"id": "connect", "status": "passed", "message": "The endpoint responded"})
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _probe_failure(
            "response",
            "The endpoint did not return valid JSON",
            normalized_url,
            checks,
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return _probe_failure(
            "response",
            "The /models response did not contain a model list",
            normalized_url,
            checks,
        )
    models = tuple(
        item["id"]
        for item in payload["data"][:100]
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and _safe_model_name(item["id"])
    )
    if not models:
        return _probe_failure(
            "models",
            "The endpoint is reachable but did not advertise any models",
            normalized_url,
            checks,
        )
    checks.append(
        {
            "id": "models",
            "status": "passed",
            "message": f"The endpoint advertised {len(models)} model{'s' if len(models) != 1 else ''}",
        }
    )
    if selected_model is not None and selected_model not in models:
        checks.append(
            {
                "id": "model",
                "status": "failed",
                "message": "The selected model was not in the advertised model list",
            }
        )
        return SummaryProbeResult(
            ok=False,
            stage="model",
            message="The endpoint is reachable, but the selected model was not found",
            base_url=normalized_url,
            models=models,
            selected_model=selected_model,
            model_available=False,
            checks=tuple(checks),
        )
    if selected_model is not None:
        checks.append({"id": "model", "status": "passed", "message": "The selected model is available"})
    return SummaryProbeResult(
        ok=True,
        stage="ready",
        message="The summary model endpoint is ready",
        base_url=normalized_url,
        models=models,
        selected_model=selected_model,
        model_available=True if selected_model is not None else None,
        checks=tuple(checks),
    )


def validate_outbound_destination(value: str) -> str:
    """Apply the probe's destination policy to a real provider request URL."""

    normalized_url = normalize_base_url(value)
    parsed = urlsplit(normalized_url)
    try:
        _check_resolved_addresses(
            parsed.hostname or "",
            parsed.port or (443 if parsed.scheme == "https" else 80),
            scheme=parsed.scheme,
        )
    except _ProbeFailure as exc:
        raise SummaryConfigurationError(exc.message) from exc
    return normalized_url


@dataclass(frozen=True, slots=True)
class _ProbeFailure(Exception):
    stage: str
    message: str


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent a probe from following a redirect to an unintended destination."""

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _open_without_redirects(request: urllib.request.Request, *, timeout: float) -> Any:
    # Replace urllib's ambient proxy handler.  A machine-local probe must not
    # silently send a loopback/private URL through a process-wide proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirectHandler)
    return opener.open(request, timeout=timeout)


def _check_resolved_addresses(hostname: str, port: int, *, scheme: str) -> None:
    if not hostname:
        raise _ProbeFailure("resolve", "The endpoint host is missing")
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror) as exc:
        raise _ProbeFailure("resolve", "The endpoint host could not be resolved") from exc
    if not addresses:
        raise _ProbeFailure("resolve", "The endpoint host did not resolve to an address")
    seen: set[str] = set()
    has_public_address = False
    has_private_address = False
    for address in addresses:
        raw_ip = address[4][0]
        if raw_ip in seen:
            continue
        seen.add(raw_ip)
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise _ProbeFailure("resolve", "The endpoint resolved to an invalid address") from exc
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if ip.is_unspecified or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise _ProbeFailure(
                "resolve",
                "The endpoint resolves to a reserved or link-local address, which is blocked",
            )
        is_private = ip.is_loopback or ip.is_private or _is_tailscale_address(ip)
        has_private_address = has_private_address or is_private
        has_public_address = has_public_address or ip.is_global
    # HTTP is acceptable for a local/private model server, but a public endpoint
    # must use HTTPS so credentials supplied explicitly for a probe are not sent
    # over the network in clear text.  A mixed DNS answer is rejected because it
    # would make the destination ambiguous and weaken the preflight SSRF check.
    if has_public_address and scheme != "https":
        raise _ProbeFailure("network", "Public summary endpoints must use https")
    if has_public_address and has_private_address:
        raise _ProbeFailure("network", "The endpoint resolves to mixed public and private addresses")


def _is_tailscale_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether an address is in Tailscale's CGNAT range."""

    return ip.version == 4 and ipaddress.ip_address("100.64.0.0") <= ip <= ipaddress.ip_address(
        "100.127.255.255"
    )


def _probe_failure(
    stage: str,
    message: str,
    base_url: str | None,
    checks: list[dict[str, str]],
) -> SummaryProbeResult:
    checks.append({"id": stage, "status": "failed", "message": message})
    return SummaryProbeResult(
        ok=False,
        stage=stage,
        message=message,
        base_url=base_url,
        checks=tuple(checks),
    )


def _http_message(status: int) -> str:
    if status in {401, 403}:
        return "The endpoint rejected the probe; check its API key or access policy"
    if status == 404:
        return "The endpoint does not expose the expected /models route"
    return f"The endpoint returned HTTP {status}"


def _validated_text(value: str, *, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise SummaryConfigurationError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise SummaryConfigurationError(f"{field} is required")
    if len(text) > limit:
        raise SummaryConfigurationError(f"{field} is too long")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in text):
        raise SummaryConfigurationError(f"{field} must not contain control characters")
    return text


def _safe_model_name(value: str) -> bool:
    try:
        _validated_text(value, field="model", limit=MAX_MODEL_LENGTH)
    except SummaryConfigurationError:
        return False
    return True


def _safe_optional_model(value: str) -> str | None:
    if not value:
        return None
    return value if _safe_model_name(value) else None


def _public_text(value: object, *, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = "".join(character for character in text if ord(character) >= 0x20 and ord(character) != 0x7F)
    return text[:limit] or None


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _owned_by_current_user(path: Path) -> bool:
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return True
    try:
        return path.stat().st_uid == getuid()
    except OSError as exc:
        raise SummaryConfigurationError("summary provider runtime file could not be inspected") from exc


def _now() -> str:
    return datetime.now(UTC).isoformat()
