#!/usr/bin/env python3
"""Install portable recall guidance with backups, preserving MCP configuration."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    """Copy guidance to current and compatibility skill locations with receipts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'skills/chatreview-recall')
    parser.add_argument('--home', type=Path, default=Path.home())
    args = parser.parse_args()
    source = args.source.resolve()
    files = sorted(path for path in source.rglob('*') if path.is_file())
    if not (source / 'SKILL.md').is_file() or not files:
        parser.error('source must contain the complete chatreview-recall skill')
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    backup = args.home / '.codex/skill-backups' / f'chatreview-recall-{stamp}'
    backup.mkdir(parents=True, mode=0o700)
    receipts = []
    for location in ('.agents/skills', '.codex/skills'):
        target = args.home / location / 'chatreview-recall'
        if target.exists():
            shutil.copytree(target, backup / location.replace('/', '-'))
        target.mkdir(parents=True, exist_ok=True)
        for path in files:
            relative = path.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f'Installed skill verification failed: {relative}')
        receipts.append(str(target))
    print(json.dumps({'installed': receipts, 'backup': str(backup),
                      'guidance_sha256': hashlib.sha256((source / 'SKILL.md').read_bytes()).hexdigest(),
                      'mcp_configuration_changed': False}))


if __name__ == '__main__':
    main()
