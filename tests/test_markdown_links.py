from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"

# Matches markdown links [label](target), but excludes images ![alt](target)
LINK_PATTERN = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")


def extract_local_links(content: str) -> list[str]:
    """Extract relative local file targets from markdown content.

    Ignores external URLs (http, https), mailto:, pure anchors (#...),
    and image links (![...](...)).
    """
    targets: list[str] = []
    for match in LINK_PATTERN.finditer(content):
        raw_target = match.group(2).strip()

        # Handle optional title attribute, e.g. [text](link "title")
        if " " in raw_target and not raw_target.startswith("<"):
            raw_target = raw_target.split()[0]
        raw_target = raw_target.strip("<>")

        # Ignore external links, mailto, and anchor-only links
        if (
            raw_target.startswith(("#", "http://", "https://", "mailto:"))
            or "://" in raw_target
        ):
            continue

        # Strip anchor portion, e.g. path/to/file.md#section -> path/to/file.md
        path_part = raw_target.split("#", 1)[0]
        if not path_part:
            continue

        targets.append(path_part)
    return targets


def find_target_path(source_file: Path, target_str: str, root_dir: Path) -> Path:
    """Resolve a target relative link to an absolute filesystem Path."""
    decoded = urllib.parse.unquote(target_str)
    if decoded.startswith("/"):
        return (root_dir / decoded.lstrip("/")).resolve()
    return (source_file.parent / decoded).resolve()


def test_markdown_local_relative_links() -> None:
    """Validate all relative links in root Markdown files and docs/**/*.md exist."""
    root_md_files = [p for p in REPO_ROOT.glob("*.md") if p.is_file()]
    docs_md_files = (
        [p for p in DOCS_DIR.rglob("*.md") if p.is_file()]
        if DOCS_DIR.exists()
        else []
    )
    all_md_files = root_md_files + docs_md_files

    assert all_md_files, "Expected to find root or docs markdown files to validate"

    broken_links: list[str] = []
    for doc in all_md_files:
        content = doc.read_text(encoding="utf-8")
        targets = extract_local_links(content)
        for target in targets:
            resolved = find_target_path(doc, target, REPO_ROOT)
            if not resolved.exists():
                rel_doc = doc.relative_to(REPO_ROOT)
                broken_links.append(
                    f"{rel_doc}: broken link '{target}' -> target '{resolved}' does not exist"
                )

    assert not broken_links, (
        f"Found {len(broken_links)} broken markdown links:\n"
        + "\n".join(broken_links)
    )


def test_extract_local_links_ignores_external_and_mailto() -> None:
    content = """
    Check [GitHub](https://github.com) and [Insecure](http://example.com).
    Also [Email us](mailto:test@example.com).
    """
    assert extract_local_links(content) == []


def test_extract_local_links_ignores_images() -> None:
    content = """
    Here is an image: ![Diagram](images/arch.png).
    Here is a link: [Architecture](docs/ARCHITECTURE.md).
    """
    assert extract_local_links(content) == ["docs/ARCHITECTURE.md"]


def test_extract_local_links_strips_anchors() -> None:
    content = """
    See [Deployment Guide](docs/DEPLOYMENT.md#prerequisites) and [Top](#top).
    """
    assert extract_local_links(content) == ["docs/DEPLOYMENT.md"]


def test_find_target_path_decodes_spaces_and_url_encoding(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("dummy", encoding="utf-8")
    target_file = tmp_path / "my folder" / "sample file.md"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("target", encoding="utf-8")

    resolved = find_target_path(doc, "my%20folder/sample%20file.md", tmp_path)
    assert resolved.exists()
    assert resolved == target_file.resolve()


def test_validation_reports_missing_target(tmp_path: Path) -> None:
    doc = tmp_path / "test.md"
    doc.write_text("Link to [missing](non_existent_file.md)", encoding="utf-8")
    resolved = find_target_path(doc, "non_existent_file.md", tmp_path)
    assert not resolved.exists()
