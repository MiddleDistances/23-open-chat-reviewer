# Security policy

## Supported versions

Until the first stable release, security fixes are applied to the latest `main` branch.

## Reporting a vulnerability

Do not file a public issue containing a vulnerability, credential, or chat excerpt. Use
GitHub's private vulnerability reporting for the published repository, or contact the
maintainer through the private address listed in the repository's GitHub security tab.

Include affected versions, impact, reproduction steps using synthetic data, and any
suggested mitigation. Remove secrets and personal archive content.

## Deployment boundary

Open Chat Reviewer stores highly sensitive conversation material. It binds to loopback by
default and does not implement multi-user authentication. Operators are responsible for
TLS, authentication, access control, database encryption/backups, key rotation, and
provider data-retention review when exposing it beyond one machine.

Never commit `.chatreview/`, raw JSONL, database URLs, API keys, or generated exports.
