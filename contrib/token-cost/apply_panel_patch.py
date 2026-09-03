#!/usr/bin/env python3
"""Add a "Token cost" tab to the Open Chat Reviewer web application.

Idempotent: running it twice changes nothing. Run it again after any
scripts/update.sh that reverts the two edited files.

    python3 apply_panel_patch.py [--repo ~/open-chat-reviewer] [--check]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

MARK = "token_panel"

API_ANCHOR = '    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"'
API_INSERT = '''    @app.get("/token-report", include_in_schema=False)
    def token_report_panel() -> Response:
        """Live token cost report. Local addition; see chatreview/token_panel.py."""
        from chatreview.token_panel import render_html

        return Response(render_html(settings.database_url), media_type="text/html; charset=utf-8")

'''

TSX_EDITS = [
    (  # 1. icon import
        "  CircleGauge,\n",
        "  CircleGauge,\n  Coins,\n",
        "Coins,",
    ),
    (  # 2. the embedded page
        "const navigation = [",
        '''function TokenCostPage() {
  return (
    <iframe
      title="Token cost"
      src="/token-report"
      style={{ width: "100%", height: "calc(100vh - 2rem)", border: 0, display: "block" }}
    />
  );
}

const navigation = [''',
        "function TokenCostPage()",
    ),
    (  # 3. sidebar entry, in the Work archive group
        '      { to: "/archive-status", label: "Archive status", icon: Archive, basic: false },\n',
        '      { to: "/archive-status", label: "Archive status", icon: Archive, basic: false },\n'
        '      { to: "/token-cost", label: "Token cost", icon: Coins, basic: true },\n',
        '{ to: "/token-cost"',
    ),
    (  # 4. the route
        '            <Route path="/archive-status" element={<WorkArchivePage />} />\n',
        '            <Route path="/archive-status" element={<WorkArchivePage />} />\n'
        '            <Route path="/token-cost" element={<TokenCostPage />} />\n',
        'path="/token-cost"',
    ),
]


def patch(path: Path, edits, check: bool) -> str:
    text = path.read_text(encoding="utf-8")
    applied = []
    for old, new, marker in edits:
        if marker in text:
            continue
        if old not in text:
            return f"FAILED: anchor not found in {path.name}: {old.strip()[:60]}"
        text = text.replace(old, new, 1)
        applied.append(marker)
    if not applied:
        return f"already patched: {path.name}"
    if not check:
        backup = path.with_suffix(path.suffix + ".orig")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(text, encoding="utf-8")
    return f"patched {path.name} ({len(applied)} edit(s))"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(Path.home() / "open-chat-reviewer"))
    ap.add_argument("--panel", default="", help="source token_panel.py; defaults to the tracked copy")
    ap.add_argument("--check", action="store_true", help="report without writing")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    api = repo / "src" / "chatreview" / "api.py"
    tsx = repo / "web" / "src" / "App.tsx"
    dest = repo / "src" / "chatreview" / "token_panel.py"
    for p in (api, tsx):
        if not p.is_file():
            sys.exit(f"not found: {p}")

    if args.panel:
        panel = Path(args.panel).expanduser().resolve()
        if not panel.is_file():
            sys.exit(f"token_panel.py not found at {panel}")
        if not args.check:
            shutil.copy2(panel, dest)
        print(f"module    -> {dest} (copied from {panel})")
    elif dest.is_file():
        print(f"module    -> {dest} (already present)")
    else:
        sys.exit(f"{dest} is missing and no --panel was given.")

    api_text = api.read_text(encoding="utf-8")
    if MARK in api_text:
        print("already patched: api.py")
    elif API_ANCHOR not in api_text:
        sys.exit("FAILED: anchor not found in api.py; upstream layout changed.")
    elif not args.check:
        backup = api.with_suffix(".py.orig")
        if not backup.exists():
            shutil.copy2(api, backup)
        api.write_text(api_text.replace(API_ANCHOR, API_INSERT + API_ANCHOR, 1), encoding="utf-8")
        print("patched api.py (1 edit)")
    else:
        print("would patch api.py")

    result = patch(tsx, TSX_EDITS, args.check)
    print(result)
    if result.startswith("FAILED"):
        sys.exit(1)


if __name__ == "__main__":
    main()
