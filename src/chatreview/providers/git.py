from __future__ import annotations

import fcntl
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import orjson

from chatreview.providers.base import ProviderAdapter, add_fragment, stable_hash
from chatreview.registry import normalize_git_remote
from chatreview.types import Artifact, ParsedRecord, SourceSpec, TextFragment

GIT_RECORD_SCHEMA = "chatreview.git.v1"
HASH_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
REFLOG_PATTERN = re.compile(
    r"^(?P<old>[0-9a-f]{40,64}) (?P<new>[0-9a-f]{40,64}) "
    r"(?P<actor>.*) <(?P<email>[^>]*)> (?P<epoch>\d+) (?P<offset>[+-]\d{4})"
    r"(?:\t(?P<action>.*))?$"
)
SKIP_DIRECTORIES = {
    ".chatreview",
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
    "venv",
}
ELIGIBLE_REFLOG_PREFIXES = (
    "branch",
    "checkout",
    "cherry-pick",
    "clone",
    "commit",
    "merge",
    "pull",
    "rebase",
    "reset",
    "revert",
)


@dataclass(frozen=True, slots=True)
class GitCheckout:
    path: Path
    git_dir: Path
    common_dir: Path
    first_seen_ns: int | None


@dataclass(slots=True)
class GitRepository:
    identity: str
    repository_url: str | None
    checkouts: list[GitCheckout] = field(default_factory=list)
    commits: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def primary(self) -> GitCheckout:
        return min(
            self.checkouts,
            key=lambda item: (
                item.first_seen_ns if item.first_seen_ns is not None else 2**63 - 1,
                len(item.path.parts),
                str(item.path),
            ),
        )

    @property
    def first_seen_ns(self) -> int | None:
        values = [item.first_seen_ns for item in self.checkouts if item.first_seen_ns is not None]
        return min(values) if values else None


class GitAdapter(ProviderAdapter):
    """Project local Git object and reflog evidence into deterministic JSONL sources."""

    name = "git"
    parser_version = 1

    def __init__(self, root: Path, archive_root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.archive_root = archive_root.expanduser().resolve()

    def prepare(self) -> list[SourceSpec]:
        """Refresh generated evidence without writing anywhere under the project root."""

        self.archive_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.archive_root / ".index.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            repositories = _discover_repositories(self.root)
            names, emails = _configured_identities(repositories)
            for repository in repositories:
                repository.commits = _repository_commits(repository, names=names, emails=emails)
            owners = _commit_owners(repositories)
            sources = []
            for repository in repositories:
                path = self.archive_root / f"{stable_hash(repository.identity)}.jsonl"
                payload = _render_repository(repository, owners=owners)
                _write_if_changed(path, payload)
                sources.append(
                    SourceSpec(
                        self.name,
                        path,
                        "repository",
                        _source_provenance(self.root, repository),
                    )
                )
            catalog = {
                "schema": GIT_RECORD_SCHEMA,
                "root": str(self.root),
                "sources": [
                    {"path": str(source.path), "provenance": source.provenance}
                    for source in sorted(sources, key=lambda item: str(item.path))
                ],
            }
            _write_if_changed(
                self.archive_root / "catalog.json",
                orjson.dumps(catalog, option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE),
            )
            return sorted(sources, key=lambda item: str(item.path))

    def discover(self) -> list[SourceSpec]:
        catalog_path = self.archive_root / "catalog.json"
        if not catalog_path.is_file():
            return self.prepare()
        try:
            catalog = orjson.loads(catalog_path.read_bytes())
        except (OSError, orjson.JSONDecodeError):
            return self.prepare()
        if not isinstance(catalog, dict) or catalog.get("root") != str(self.root):
            return self.prepare()
        sources = []
        for value in catalog.get("sources", []):
            entry = value if isinstance(value, dict) else {"path": value, "provenance": {}}
            path = Path(str(entry.get("path")))
            if path.is_file():
                provenance = entry.get("provenance")
                sources.append(
                    SourceSpec(
                        self.name,
                        path,
                        "repository",
                        provenance if isinstance(provenance, dict) else {},
                    )
                )
        return sorted(sources, key=lambda item: str(item.path))

    def parse(self, data: dict[str, Any], source: SourceSpec) -> ParsedRecord:
        del source
        if data.get("schema") != GIT_RECORD_SCHEMA:
            raise ValueError("unsupported Git evidence schema")
        record_type = _text(data.get("record_type"))
        repository = data.get("repository")
        if not record_type or not isinstance(repository, dict):
            raise ValueError("Git evidence record is missing its type or repository")
        checkout_path = _text(data.get("checkout_path")) or _text(repository.get("primary_path"))
        repository_identity = _text(repository.get("identity"))
        if not checkout_path or not repository_identity:
            raise ValueError("Git evidence record is missing checkout provenance")
        session_id = f"{repository_identity}\0{stable_hash(checkout_path)}"
        metadata = {
            "git": {
                "repository_url": repository.get("repository_url"),
                "repository_identity": repository_identity,
                "record_type": record_type,
                "workload_eligible": bool(data.get("workload_eligible")),
            }
        }
        fragments: list[TextFragment] = []
        artifacts: list[Artifact] = []
        timestamp = None
        provider_event_id: str
        subtype = record_type

        if record_type in {"commit", "inherited_commit"}:
            commit = data.get("commit")
            if not isinstance(commit, dict) or not _text(commit.get("hash")):
                raise ValueError("Git commit record has no commit hash")
            commit_hash = str(commit["hash"])
            add_fragment(fragments, artifacts, kind="commit-message", value=commit.get("message"))
            for change in commit.get("changes", []):
                if not isinstance(change, dict):
                    continue
                path = _text(change.get("path"))
                if path:
                    artifacts.append(Artifact("path", path, _text(change.get("status"))))
            artifacts.append(Artifact("git-commit", commit_hash))
            for parent in commit.get("parents", []):
                if _text(parent):
                    artifacts.append(Artifact("git-parent", str(parent)))
            ownership = data.get("ownership") if isinstance(data.get("ownership"), dict) else {}
            if record_type == "commit" and data.get("workload_eligible"):
                timestamp = _text(ownership.get("clock_timestamp"))
            provider_event_id = (
                f"git:commit:{commit_hash}"
                if record_type == "commit"
                else f"git:inherited:{repository_identity}:{commit_hash}"
            )
            metadata["git"].update(
                {
                    "commit_hash": commit_hash,
                    "author_timestamp": commit.get("author_timestamp"),
                    "committer_timestamp": commit.get("committer_timestamp"),
                    "attribution": ownership.get("attribution"),
                    "owner_repository": ownership.get("owner_repository"),
                }
            )
        elif record_type in {"reflog", "stash"}:
            reflog = data.get("reflog")
            if not isinstance(reflog, dict):
                raise ValueError("Git reflog record is missing reflog evidence")
            action = _text(reflog.get("action"))
            add_fragment(fragments, artifacts, kind="git-operation", value=action)
            ref = _text(reflog.get("ref"))
            if ref:
                artifacts.append(Artifact("git-ref", ref))
            if _text(reflog.get("new_hash")):
                artifacts.append(Artifact("git-commit", str(reflog["new_hash"])))
            timestamp = _text(reflog.get("timestamp")) if data.get("workload_eligible") else None
            provider_event_id = "git:reflog:" + stable_hash(
                orjson.dumps(
                    [
                        repository_identity,
                        checkout_path,
                        ref,
                        reflog.get("old_hash"),
                        reflog.get("new_hash"),
                        reflog.get("timestamp"),
                        action,
                    ]
                )
            )
            metadata["git"].update(
                {
                    "ref": ref,
                    "action": action,
                    "actor": reflog.get("actor"),
                    "observed_timestamp": reflog.get("timestamp"),
                }
            )
        elif record_type == "repository":
            add_fragment(
                fragments,
                artifacts,
                kind="repository",
                value=repository.get("repository_url") or checkout_path,
            )
            provider_event_id = f"git:repository:{repository_identity}:{stable_hash(checkout_path)}"
            metadata["git"].update(
                {
                    "common_dir_hash": data.get("common_dir_hash"),
                    "first_seen_timestamp": data.get("first_seen_timestamp"),
                    "first_seen_method": data.get("first_seen_method"),
                }
            )
        else:
            raise ValueError(f"unknown Git evidence record type: {record_type}")

        return ParsedRecord(
            provider=self.name,
            session_external_id=session_id,
            event_type=f"git_{record_type}",
            subtype=subtype,
            timestamp=timestamp,
            provider_event_id=provider_event_id,
            cwd=checkout_path,
            project=checkout_path,
            metadata=metadata,
            fragments=fragments,
            artifacts=artifacts,
        )

    def normalize_project(self, value: str | None) -> str | None:
        return value


def _discover_repositories(root: Path) -> list[GitRepository]:
    if not root.is_dir():
        return []
    candidates: list[Path] = []
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names if name not in SKIP_DIRECTORIES)
        if ".git" in files:
            candidates.append(Path(directory))
        git_directory = Path(directory) / ".git"
        if git_directory.is_dir():
            candidates.append(Path(directory))
    groups: dict[str, GitRepository] = {}
    seen_checkouts: set[Path] = set()
    for candidate in sorted(set(candidates)):
        top = _git_path(candidate, "--show-toplevel")
        git_dir = _git_path(candidate, "--git-dir")
        common_dir = _git_path(candidate, "--git-common-dir")
        if top is None or git_dir is None or common_dir is None or top in seen_checkouts:
            continue
        seen_checkouts.add(top)
        raw_remote = _git(candidate, "remote", "get-url", "origin")
        normalized = normalize_git_remote(raw_remote.strip()) if raw_remote else None
        repository_url = normalized[0] if normalized else None
        identity = f"remote:{repository_url}" if repository_url else f"common:{stable_hash(str(common_dir))}"
        repository = groups.setdefault(identity, GitRepository(identity, repository_url))
        repository.checkouts.append(
            GitCheckout(
                path=top,
                git_dir=git_dir,
                common_dir=common_dir,
                first_seen_ns=_birth_time_ns(common_dir),
            )
        )
    return sorted(groups.values(), key=lambda item: item.identity)


def _configured_identities(repositories: list[GitRepository]) -> tuple[set[str], set[str]]:
    names = _split_identities(os.environ.get("CHATREVIEW_GIT_AUTHOR_NAMES"))
    emails = {item.casefold() for item in _split_identities(os.environ.get("CHATREVIEW_GIT_AUTHOR_EMAILS"))}
    paths = [repository.primary.path for repository in repositories]
    paths.append(Path.cwd())
    for path in paths:
        names.update(_git_lines(path, "config", "--get-all", "user.name"))
        emails.update(item.casefold() for item in _git_lines(path, "config", "--get-all", "user.email"))
    return {item.strip() for item in names if item.strip()}, {item.strip() for item in emails if item.strip()}


def _repository_commits(
    repository: GitRepository, *, names: set[str], emails: set[str]
) -> dict[str, dict[str, Any]]:
    commits: dict[str, dict[str, Any]] = {}
    folded_names = {name.casefold() for name in names}
    for checkout in repository.checkouts:
        for value in sorted(emails | names):
            for identity_field in ("author", "committer"):
                output = _git(
                    checkout.path,
                    "log",
                    "--exclude=refs/stash",
                    "--all",
                    "--fixed-strings",
                    f"--{identity_field}={value}",
                    "--format=%x1e%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%cn%x1f%ce%x1f%cI%x1f%B",
                )
                for record in _parse_commit_log(output):
                    author_match = (
                        record["author_name"].casefold() in folded_names
                        or record["author_email"].casefold() in emails
                    )
                    committer_match = (
                        record["committer_name"].casefold() in folded_names
                        or record["committer_email"].casefold() in emails
                    )
                    if not author_match and not committer_match:
                        continue
                    record["author_match"] = author_match
                    record["committer_match"] = committer_match
                    record.setdefault("observed_checkouts", set()).add(str(checkout.path))
                    commits.setdefault(record["hash"], record)
                    commits[record["hash"]]["observed_checkouts"].add(str(checkout.path))
    changes = _changed_files(repository.primary.path, sorted(commits))
    for commit_hash, record in commits.items():
        record["observed_checkouts"] = sorted(record["observed_checkouts"])
        record["changes"] = changes.get(commit_hash, [])
    return commits


def _parse_commit_log(output: str) -> list[dict[str, Any]]:
    records = []
    for chunk in output.split("\x1e"):
        fields = chunk.lstrip("\n").split("\x1f", 8)
        if len(fields) != 9 or not HASH_PATTERN.fullmatch(fields[0]):
            continue
        commit_hash, parents, author_name, author_email, author_time = fields[:5]
        committer_name, committer_email, committer_time, message = fields[5:]
        records.append(
            {
                "hash": commit_hash,
                "parents": [value for value in parents.split() if HASH_PATTERN.fullmatch(value)],
                "author_name": author_name,
                "author_email": author_email,
                "author_timestamp": author_time,
                "committer_name": committer_name,
                "committer_email": committer_email,
                "committer_timestamp": committer_time,
                "message": message.rstrip(),
            }
        )
    return records


def _changed_files(path: Path, commit_hashes: list[str]) -> dict[str, list[dict[str, str]]]:
    if not commit_hashes:
        return {}
    process = subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "diff-tree",
            "--stdin",
            "--root",
            "-r",
            "--name-status",
            "--no-renames",
        ],
        input="\n".join(commit_hashes) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    result: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    current = None
    for line in process.stdout.splitlines():
        if HASH_PATTERN.fullmatch(line):
            current = line
            continue
        if current is None or "\t" not in line:
            continue
        status, file_path = line.split("\t", 1)
        result[current].append({"status": status, "path": file_path})
    return dict(result)


def _commit_owners(repositories: list[GitRepository]) -> dict[str, str]:
    candidates: defaultdict[str, list[GitRepository]] = defaultdict(list)
    for repository in repositories:
        for commit_hash in repository.commits:
            candidates[commit_hash].append(repository)
    owners = {}
    for commit_hash, values in candidates.items():
        owner = min(
            values,
            key=lambda item: (
                item.first_seen_ns if item.first_seen_ns is not None else 2**63 - 1,
                item.identity,
            ),
        )
        owners[commit_hash] = owner.identity
    return owners


def _render_repository(repository: GitRepository, *, owners: dict[str, str]) -> bytes:
    repo = {
        "identity": repository.identity,
        "repository_url": repository.repository_url,
        "primary_path": str(repository.primary.path),
        "checkout_paths": sorted(str(item.path) for item in repository.checkouts),
    }
    records: list[dict[str, Any]] = []
    for checkout in sorted(repository.checkouts, key=lambda item: str(item.path)):
        first_seen, method = _first_seen(checkout)
        records.append(
            {
                "schema": GIT_RECORD_SCHEMA,
                "record_type": "repository",
                "repository": repo,
                "checkout_path": str(checkout.path),
                "common_dir_hash": stable_hash(str(checkout.common_dir)),
                "first_seen_timestamp": first_seen,
                "first_seen_method": method,
                "workload_eligible": False,
            }
        )
    for commit_hash, commit in sorted(
        repository.commits.items(), key=lambda item: (item[1]["committer_timestamp"], item[0])
    ):
        owner = owners[commit_hash]
        is_owner = owner == repository.identity
        attribution = "committer" if commit["committer_match"] else "author"
        timestamp = (
            commit["committer_timestamp"] if commit["committer_match"] else commit["author_timestamp"]
        )
        records.append(
            {
                "schema": GIT_RECORD_SCHEMA,
                "record_type": "commit" if is_owner else "inherited_commit",
                "repository": repo,
                "checkout_path": str(repository.primary.path),
                "workload_eligible": is_owner,
                "ownership": {
                    "owner_repository": owner,
                    "attribution": attribution,
                    "clock_timestamp": timestamp if is_owner else None,
                },
                "commit": commit,
            }
        )
    for checkout in sorted(repository.checkouts, key=lambda item: str(item.path)):
        records.extend(_reflog_records(repository, checkout, repo))
    return b"".join(
        orjson.dumps(record, option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE)
        for record in records
    )


def _source_provenance(root: Path, repository: GitRepository) -> dict[str, Any]:
    return {
        "git_root": str(root),
        "repository_identity": repository.identity,
        "repository_url": repository.repository_url,
        "checkout_paths": sorted(str(item.path) for item in repository.checkouts),
    }


def _reflog_records(
    repository: GitRepository, checkout: GitCheckout, repo: dict[str, Any]
) -> list[dict[str, Any]]:
    records = []
    roots = [(checkout.common_dir / "logs", "common")]
    if checkout.git_dir != checkout.common_dir:
        roots.append((checkout.git_dir / "logs", "worktree"))
    seen_files: set[Path] = set()
    for logs_root, scope in roots:
        if not logs_root.is_dir():
            continue
        for path in sorted(item for item in logs_root.rglob("*") if item.is_file()):
            resolved = path.resolve()
            if resolved in seen_files:
                continue
            seen_files.add(resolved)
            ref = path.relative_to(logs_root).as_posix()
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, start=1):
                match = REFLOG_PATTERN.match(line)
                if not match:
                    continue
                action = match.group("action") or ""
                timestamp = _reflog_timestamp(match.group("epoch"), match.group("offset"))
                is_stash = ref == "refs/stash"
                eligible_ref = ref == "HEAD" or ref.startswith("refs/heads/")
                eligible_action = action.casefold().startswith(ELIGIBLE_REFLOG_PREFIXES)
                record_type = "stash" if is_stash else "reflog"
                records.append(
                    {
                        "schema": GIT_RECORD_SCHEMA,
                        "record_type": record_type,
                        "repository": repo,
                        "checkout_path": str(checkout.path),
                        "workload_eligible": is_stash or (eligible_ref and eligible_action),
                        "reflog": {
                            "scope": scope,
                            "log_path_hash": stable_hash(str(path)),
                            "line_no": line_no,
                            "ref": ref,
                            "old_hash": match.group("old"),
                            "new_hash": match.group("new"),
                            "actor": match.group("actor"),
                            "actor_email": match.group("email"),
                            "timestamp": timestamp,
                            "action": action,
                        },
                    }
                )
    return sorted(
        records,
        key=lambda item: (
            item["reflog"]["timestamp"],
            item["checkout_path"],
            item["reflog"]["ref"],
            item["reflog"]["line_no"],
        ),
    )


def _first_seen(checkout: GitCheckout) -> tuple[str | None, str | None]:
    if checkout.first_seen_ns is None:
        return None, None
    return datetime.fromtimestamp(checkout.first_seen_ns / 1_000_000_000, UTC).isoformat(), "git-dir-birth"


def _birth_time_ns(path: Path) -> int | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    value = getattr(stat, "st_birthtime", None)
    if value is None or value <= 0:
        return None
    return int(value * 1_000_000_000)


def _reflog_timestamp(epoch: str, offset: str) -> str:
    sign = 1 if offset.startswith("+") else -1
    hours = int(offset[1:3])
    minutes = int(offset[3:5])
    zone = timezone(sign * timedelta(hours=hours, minutes=minutes))
    return datetime.fromtimestamp(int(epoch), zone).isoformat()


def _git_path(path: Path, argument: str) -> Path | None:
    value = _git(path, "rev-parse", "--path-format=absolute", argument).strip()
    return Path(value).resolve() if value else None


def _git_lines(path: Path, *arguments: str) -> set[str]:
    return {line.strip() for line in _git(path, *arguments).splitlines() if line.strip()}


def _git(path: Path, *arguments: str) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(path), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return process.stdout if process.returncode == 0 else ""


def _split_identities(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in re.split(r"[,;\n]", value) if item.strip()}


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _write_if_changed(path: Path, payload: bytes) -> None:
    try:
        if path.is_file() and path.read_bytes() == payload:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)
