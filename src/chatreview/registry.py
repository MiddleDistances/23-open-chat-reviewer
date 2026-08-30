from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from chatreview.db import Session
from chatreview.providers.base import stable_hash

SCP_REMOTE = re.compile(r"^(?:[^@]+@)?(?P<host>[^:]+):(?P<path>.+)$")


@dataclass(frozen=True, slots=True)
class RegistrySummary:
    projects: int
    aliases: int
    linked_sessions: int
    unresolved_projects: int
    unresolved_activities: int
    unresolved_contributors: int


def normalize_git_remote(value: str) -> tuple[str, str, str, str] | None:
    """Return canonical URL, host, owner and repository for common Git remotes."""

    raw = value.strip()
    if not raw:
        return None
    match = SCP_REMOTE.match(raw) if "://" not in raw else None
    if match:
        host = match.group("host").casefold()
        path = match.group("path")
    else:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = (parsed.hostname or "").casefold()
        path = parsed.path
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2 or not host:
        return None
    owner = "/".join(parts[:-1]).casefold()
    repository = parts[-1].removesuffix(".git").casefold()
    if not repository:
        return None
    canonical = f"https://{host}/{owner}/{repository}"
    return canonical, host, owner, repository


def rebuild_registry(connection: Session) -> RegistrySummary:
    """Resolve canonical projects and machine path aliases from archived sessions."""

    sessions = connection.execute(
        """
        SELECT id, machine_id, provider, project, cwd, started_at, metadata_json
        FROM sessions ORDER BY id
        """
    ).fetchall()
    staged: list[tuple[Any, ...]] = []
    for session in sessions:
        metadata = session["metadata_json"] if isinstance(session["metadata_json"], dict) else {}
        git = metadata.get("git") if isinstance(metadata, dict) else None
        remote = git.get("repository_url") if isinstance(git, dict) else None
        normalized_remote = normalize_git_remote(str(remote)) if remote else None
        raw_path = str(session["cwd"] or session["project"] or "").strip()
        if normalized_remote:
            repository_url, host, owner, repository = normalized_remote
            project_key = stable_hash(f"git\0{host}\0{owner}\0{repository}")
            name = repository
            unresolved = False
        elif raw_path:
            normalized_path = _normalize_path(raw_path)
            repository_url = host = owner = None
            repository = PurePosixPath(normalized_path).name or normalized_path
            project_key = stable_hash(f"path\0{normalized_path.casefold()}")
            name = repository
            unresolved = True
        else:
            project_key = stable_hash("project\0unallocated")
            name = "Unallocated"
            repository_url = host = owner = repository = None
            unresolved = True
        staged.append(
            (
                int(session["id"]),
                session["machine_id"],
                session["provider"],
                session["started_at"],
                project_key,
                name,
                repository_url,
                host,
                owner,
                repository,
                unresolved,
                raw_path or None,
                _normalize_path(raw_path) if raw_path else None,
            )
        )

    connection.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS registry_session_stage (
            session_id bigint PRIMARY KEY, machine_id uuid,
            provider text NOT NULL, observed_at timestamptz, project_key text NOT NULL,
            name text NOT NULL, repository_url text, repository_host text,
            repository_owner text, repository_name text, is_unresolved boolean NOT NULL,
            raw_path text, normalized_path text
        ) ON COMMIT DELETE ROWS;
        TRUNCATE registry_session_stage
        """
    )
    connection.copy_rows(
        "registry_session_stage",
        (
            "session_id",
            "machine_id",
            "provider",
            "observed_at",
            "project_key",
            "name",
            "repository_url",
            "repository_host",
            "repository_owner",
            "repository_name",
            "is_unresolved",
            "raw_path",
            "normalized_path",
        ),
        staged,
    )
    connection.execute(
        """
        INSERT INTO projects(
            project_key, name, repository_url, repository_host,
            repository_owner, repository_name, is_unresolved
        )
        SELECT candidate.project_key, candidate.name, candidate.repository_url,
               candidate.repository_host, candidate.repository_owner,
               candidate.repository_name, candidate.is_unresolved
        FROM (
            SELECT DISTINCT ON (stage.project_key)
                   stage.project_key, stage.name, stage.repository_url,
                   stage.repository_host, stage.repository_owner,
                   stage.repository_name, stage.is_unresolved
            FROM registry_session_stage stage
            WHERE stage.repository_url IS NOT NULL
               OR stage.normalized_path IS NULL
               OR NOT EXISTS (
                    SELECT 1 FROM project_aliases alias
                    WHERE (alias.machine_id IS NULL OR alias.machine_id=stage.machine_id)
                      AND (alias.provider IS NULL OR alias.provider=stage.provider)
                      AND (alias.path_prefix=stage.normalized_path
                           OR stage.normalized_path LIKE alias.path_prefix || '/%')
                      AND COALESCE(stage.observed_at, clock_timestamp()) >= alias.effective_from
                      AND COALESCE(stage.observed_at, clock_timestamp()) < alias.effective_to
               )
            ORDER BY stage.project_key, stage.session_id
        ) candidate
        ON CONFLICT (project_key) DO UPDATE SET
            name=EXCLUDED.name,
            repository_url=COALESCE(EXCLUDED.repository_url, projects.repository_url),
            repository_host=COALESCE(EXCLUDED.repository_host, projects.repository_host),
            repository_owner=COALESCE(EXCLUDED.repository_owner, projects.repository_owner),
            repository_name=COALESCE(EXCLUDED.repository_name, projects.repository_name),
            is_unresolved=projects.is_unresolved AND EXCLUDED.is_unresolved,
            updated_at=clock_timestamp()
        """
    )
    # Git repository sessions carry a verified canonical remote and enumerate the
    # checkout roots on this machine. Register those paths as provider-neutral
    # aliases before resolving chat sessions so Codex, Claude, and Gemini cwd values
    # converge on the same repository during this reconciliation pass.
    connection.execute(
        """
        INSERT INTO project_aliases(project_id, machine_id, path_prefix, provider, alias)
        SELECT DISTINCT project.id, stage.machine_id, stage.normalized_path, NULL, stage.raw_path
        FROM registry_session_stage stage
        JOIN projects project ON project.project_key=stage.project_key
        WHERE stage.provider='git'
          AND stage.repository_url IS NOT NULL
          AND stage.normalized_path IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    connection.execute(
        """
        WITH resolved AS (
            SELECT stage.session_id,
                   COALESCE(
                       CASE WHEN stage.repository_url IS NULL
                                  AND stage.normalized_path IS NOT NULL THEN (
                           SELECT alias.project_id FROM project_aliases alias
                           WHERE (alias.machine_id IS NULL OR alias.machine_id=stage.machine_id)
                             AND (alias.provider IS NULL OR alias.provider=stage.provider)
                             AND (alias.path_prefix=stage.normalized_path
                                  OR stage.normalized_path LIKE alias.path_prefix || '/%')
                             AND COALESCE(stage.observed_at, clock_timestamp()) >= alias.effective_from
                             AND COALESCE(stage.observed_at, clock_timestamp()) < alias.effective_to
                           ORDER BY (alias.machine_id IS NOT NULL) DESC,
                                    (alias.provider IS NOT NULL) DESC,
                                    length(alias.path_prefix) DESC,
                                    alias.effective_from DESC, alias.id DESC
                           LIMIT 1
                       ) END,
                       project.id
                   ) AS project_id
            FROM registry_session_stage stage
            LEFT JOIN projects project ON project.project_key=stage.project_key
        )
        UPDATE sessions session SET project_id=resolved.project_id
        FROM resolved
        WHERE session.id=resolved.session_id
          AND resolved.project_id IS NOT NULL
          AND session.project_id IS DISTINCT FROM resolved.project_id
        """
    )
    aliases = connection.execute(
        """
        INSERT INTO project_aliases(project_id, machine_id, path_prefix, provider, alias)
        SELECT DISTINCT session.project_id, stage.machine_id, stage.normalized_path,
                        CASE WHEN stage.provider='git' THEN NULL ELSE stage.provider END,
                        stage.raw_path
        FROM registry_session_stage stage
        JOIN sessions session ON session.id=stage.session_id
        WHERE stage.raw_path IS NOT NULL AND session.project_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    ).rowcount
    connection.commit()
    return registry_summary(
        connection,
        aliases_added=aliases,
        linked_sessions=len(sessions),
    )


def apply_contributor_rules(connection: Session) -> int:
    """Apply the most specific effective attribution rule to each session."""

    cursor = connection.execute(
        """
        WITH resolved AS (
            SELECT session.id,
                   (
                       SELECT rule.contributor_id
                       FROM contributor_rules rule
                       WHERE rule.machine_id=session.machine_id
                         AND (rule.provider IS NULL OR rule.provider=session.provider)
                         AND (rule.path_prefix IS NULL OR session.cwd LIKE rule.path_prefix || '%')
                         AND COALESCE(session.started_at, clock_timestamp()) >= rule.effective_from
                         AND COALESCE(session.started_at, clock_timestamp()) < rule.effective_to
                       ORDER BY length(COALESCE(rule.path_prefix, '')) DESC,
                                rule.effective_from DESC, rule.id DESC
                       LIMIT 1
                   ) AS contributor_id
            FROM sessions session
        )
        UPDATE sessions session SET contributor_id=resolved.contributor_id
        FROM resolved
        WHERE session.id=resolved.id AND resolved.contributor_id IS NOT NULL
          AND session.contributor_id IS DISTINCT FROM resolved.contributor_id
        """
    )
    connection.commit()
    return cursor.rowcount


def registry_summary(
    connection: Session,
    *,
    aliases_added: int = 0,
    linked_sessions: int = 0,
) -> RegistrySummary:
    row = connection.execute(
        """
        SELECT (SELECT COUNT(*) FROM projects) AS projects,
               (SELECT COUNT(*) FROM project_aliases) AS aliases,
               (SELECT COUNT(*) FROM projects WHERE is_unresolved) AS unresolved_projects,
               (SELECT COUNT(*) FROM sessions WHERE contributor_id IS NULL) AS unresolved_contributors,
               (
                   SELECT COUNT(*) FROM sessions session
                   WHERE session.project_id IS NULL OR NOT EXISTS (
                       SELECT 1 FROM project_default_activities defaults
                       WHERE defaults.project_id=session.project_id
                         AND COALESCE(session.started_at, clock_timestamp()) >= defaults.effective_from
                         AND COALESCE(session.started_at, clock_timestamp()) < defaults.effective_to
                   )
               ) AS unresolved_activities
        """
    ).fetchone()
    assert row is not None
    return RegistrySummary(
        projects=int(row["projects"]),
        aliases=int(row["aliases"]),
        linked_sessions=linked_sessions,
        unresolved_projects=int(row["unresolved_projects"]),
        unresolved_activities=int(row["unresolved_activities"]),
        unresolved_contributors=int(row["unresolved_contributors"]),
    )


def list_projects(connection: Session) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT project.id, project.project_key, project.name, project.repository_url,
                   project.is_unresolved, COUNT(DISTINCT session.id) AS session_count,
                   COUNT(DISTINCT alias.id) AS alias_count,
                   activity.code AS default_activity,
                   activity.classification AS default_classification
            FROM projects project
            LEFT JOIN sessions session ON session.project_id=project.id
            LEFT JOIN project_aliases alias ON alias.project_id=project.id
            LEFT JOIN LATERAL (
                SELECT a.code, a.classification
                FROM project_default_activities defaults
                JOIN activities a ON a.id=defaults.activity_id
                WHERE defaults.project_id=project.id AND now() >= defaults.effective_from
                  AND now() < defaults.effective_to
                ORDER BY defaults.effective_from DESC LIMIT 1
            ) activity ON true
            GROUP BY project.id, activity.code, activity.classification
            ORDER BY project.is_unresolved, project.name, project.id
            """
        )
    ]


def list_project_aliases(connection: Session) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT alias.id, alias.project_id, alias.machine_id, alias.path_prefix,
                   alias.provider, alias.alias,
                   alias.effective_from::text AS effective_from,
                   alias.effective_to::text AS effective_to, alias.created_at,
                   project.project_key, project.name AS project,
                   machine.name AS machine_name
            FROM project_aliases alias
            JOIN projects project ON project.id=alias.project_id
            LEFT JOIN machines machine ON machine.id=alias.machine_id
            ORDER BY length(COALESCE(alias.path_prefix, '')) DESC, alias.id DESC
            """
        )
    ]


def save_project_alias(
    connection: Session,
    *,
    project_id: int,
    path_prefix: str,
    machine_id: str | None = None,
    provider: str | None = None,
    alias: str | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> dict[str, Any]:
    normalized = _normalize_path(path_prefix)
    row = connection.execute(
        """
        INSERT INTO project_aliases(
            project_id, machine_id, path_prefix, provider, alias,
            effective_from, effective_to
        ) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *
        """,
        (
            project_id,
            machine_id,
            normalized,
            provider,
            alias or path_prefix,
            effective_from or datetime.min.replace(tzinfo=UTC),
            effective_to or datetime.max.replace(tzinfo=UTC),
        ),
    ).fetchone()
    connection.commit()
    assert row is not None
    return dict(row)


def list_activities(connection: Session) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute("SELECT * FROM activities ORDER BY code")]


def list_contributors(connection: Session) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT contributor.id, contributor.contributor_key, contributor.display_name,
                   contributor.email, COUNT(DISTINCT session.id) AS session_count,
                   COUNT(DISTINCT rule.id) AS rule_count
            FROM contributors contributor
            LEFT JOIN sessions session ON session.contributor_id=contributor.id
            LEFT JOIN contributor_rules rule ON rule.contributor_id=contributor.id
            GROUP BY contributor.id ORDER BY contributor.display_name, contributor.id
            """
        )
    ]


def save_contributor(
    connection: Session,
    *,
    key: str,
    display_name: str,
    email: str | None = None,
) -> dict[str, Any]:
    row = connection.execute(
        """
        INSERT INTO contributors(contributor_key, display_name, email)
        VALUES (?, ?, ?)
        ON CONFLICT (contributor_key) DO UPDATE SET
            display_name=EXCLUDED.display_name, email=EXCLUDED.email,
            updated_at=clock_timestamp()
        RETURNING *
        """,
        (key.strip(), display_name.strip(), email),
    ).fetchone()
    connection.commit()
    assert row is not None
    return dict(row)


def list_contributor_rules(connection: Session) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT rule.id, rule.machine_id, rule.contributor_id, rule.path_prefix,
                   rule.provider, rule.effective_from::text AS effective_from,
                   rule.effective_to::text AS effective_to, rule.created_at,
                   machine.name AS machine_name,
                   contributor.contributor_key, contributor.display_name
            FROM contributor_rules rule
            JOIN machines machine ON machine.id=rule.machine_id
            JOIN contributors contributor ON contributor.id=rule.contributor_id
            ORDER BY machine.name, length(COALESCE(rule.path_prefix, '')) DESC,
                     rule.effective_from DESC, rule.id DESC
            """
        )
    ]


def save_contributor_rule(
    connection: Session,
    *,
    machine_id: str,
    contributor_id: int,
    path_prefix: str | None = None,
    provider: str | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> dict[str, Any]:
    row = connection.execute(
        """
        INSERT INTO contributor_rules(
            machine_id, contributor_id, path_prefix, provider, effective_from, effective_to
        ) VALUES (?, ?, ?, ?, ?, ?) RETURNING *
        """,
        (
            machine_id,
            contributor_id,
            _normalize_path(path_prefix) if path_prefix else None,
            provider,
            effective_from or datetime.min.replace(tzinfo=UTC),
            effective_to or datetime.max.replace(tzinfo=UTC),
        ),
    ).fetchone()
    apply_contributor_rules(connection)
    assert row is not None
    return dict(row)


def delete_contributor_rule(connection: Session, rule_id: int) -> bool:
    deleted = connection.execute(
        "DELETE FROM contributor_rules WHERE id=?", (rule_id,)
    ).rowcount
    connection.commit()
    return bool(deleted)


def save_activity(
    connection: Session,
    *,
    code: str,
    title: str,
    classification: str,
    reporting_period_start: date,
    reporting_period_end: date,
    description: str | None = None,
    uncertainty_or_hypothesis: str | None = None,
) -> dict[str, Any]:
    row = connection.execute(
        """
        INSERT INTO activities(
            code, title, classification, reporting_period_start, reporting_period_end,
            description, uncertainty_or_hypothesis
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (code) DO UPDATE SET
            title=EXCLUDED.title, classification=EXCLUDED.classification,
            reporting_period_start=EXCLUDED.reporting_period_start,
            reporting_period_end=EXCLUDED.reporting_period_end,
            description=EXCLUDED.description,
            uncertainty_or_hypothesis=EXCLUDED.uncertainty_or_hypothesis,
            updated_at=clock_timestamp()
        RETURNING *
        """,
        (
            code.strip(),
            title.strip(),
            classification,
            reporting_period_start,
            reporting_period_end,
            description,
            uncertainty_or_hypothesis,
        ),
    ).fetchone()
    connection.commit()
    assert row is not None
    return dict(row)


def set_project_default_activity(
    connection: Session,
    *,
    project_id: int,
    activity_id: int,
    effective_from: str,
    effective_to: str = "infinity",
) -> dict[str, Any]:
    row = connection.execute(
        """
        INSERT INTO project_default_activities(
            project_id, activity_id, effective_from, effective_to
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT (project_id, effective_from) DO UPDATE
        SET activity_id=EXCLUDED.activity_id, effective_to=EXCLUDED.effective_to
        RETURNING id, project_id, activity_id, effective_from,
                  effective_to::text AS effective_to, created_at
        """,
        (project_id, activity_id, effective_from, effective_to),
    ).fetchone()
    connection.commit()
    assert row is not None
    return dict(row)


def set_occurrence_assignment(
    connection: Session,
    *,
    episode_key: str,
    activity_id: int,
    project_id: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if connection.execute(
        "SELECT 1 FROM episodes WHERE episode_key=?", (episode_key,)
    ).fetchone() is None:
        raise KeyError(episode_key)
    row = connection.execute(
        """
        INSERT INTO occurrence_activity_overrides(
            episode_key, activity_id, project_id, note
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT (episode_key) DO UPDATE SET
            activity_id=EXCLUDED.activity_id,
            project_id=EXCLUDED.project_id,
            note=EXCLUDED.note,
            updated_at=clock_timestamp()
        RETURNING *
        """,
        (episode_key, activity_id, project_id, note),
    ).fetchone()
    connection.commit()
    assert row is not None
    return dict(row)


def unresolved_queues(connection: Session) -> dict[str, list[dict[str, Any]]]:
    return {
        "projects": [
            dict(row)
            for row in connection.execute(
                "SELECT id, project_key, name FROM projects WHERE is_unresolved ORDER BY name"
            )
        ],
        "activities": [
            dict(row)
            for row in connection.execute(
                """
                SELECT session.id AS session_id, session.session_key,
                       COALESCE(project.name, session.project) AS project
                FROM sessions session LEFT JOIN projects project ON project.id=session.project_id
                WHERE session.project_id IS NULL OR NOT EXISTS (
                    SELECT 1 FROM project_default_activities defaults
                    WHERE defaults.project_id=session.project_id
                      AND COALESCE(session.started_at, clock_timestamp()) >= defaults.effective_from
                      AND COALESCE(session.started_at, clock_timestamp()) < defaults.effective_to
                )
                ORDER BY session.started_at NULLS LAST
                """
            )
        ],
        "contributors": [
            dict(row)
            for row in connection.execute(
                """
                SELECT id AS session_id, session_key, provider, cwd, started_at
                FROM sessions WHERE contributor_id IS NULL ORDER BY started_at NULLS LAST
                """
            )
        ],
    }


def _normalize_path(value: str) -> str:
    normalized = "/" + "/".join(part for part in value.replace("\\", "/").split("/") if part)
    return normalized.rstrip("/") or "/"


def _aliased_project_id(
    connection: Session,
    *,
    machine_id: str,
    provider: str,
    raw_path: str,
    observed_at: datetime | None,
) -> int | None:
    normalized = _normalize_path(raw_path)
    row = connection.execute(
        """
        SELECT project_id FROM project_aliases
        WHERE (machine_id IS NULL OR machine_id=?)
          AND (provider IS NULL OR provider=?)
          AND (path_prefix=? OR ? LIKE path_prefix || '/%')
          AND COALESCE(?::timestamptz, clock_timestamp()) >= effective_from
          AND COALESCE(?::timestamptz, clock_timestamp()) < effective_to
        ORDER BY (machine_id IS NOT NULL) DESC, (provider IS NOT NULL) DESC,
                 length(path_prefix) DESC, effective_from DESC, id DESC
        LIMIT 1
        """,
        (machine_id, provider, normalized, normalized, observed_at, observed_at),
    ).fetchone()
    return int(row["project_id"]) if row is not None else None
