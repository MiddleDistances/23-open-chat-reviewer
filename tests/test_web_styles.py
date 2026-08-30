from __future__ import annotations

from pathlib import Path

SITE_DESIGN_CSS = (
    Path(__file__).resolve().parents[1] / "web" / "src" / "site-design.css"
)


def _rule(css: str, selector: str) -> str:
    start = css.index(selector)
    return css[start : css.index("}", start) + 1]


def test_timesheet_source_colours_override_the_intensity_theme() -> None:
    css = SITE_DESIGN_CSS.read_text(encoding="utf-8")
    intensity_rule = max(
        css.rindex(f".timesheet-day.level-{level}") for level in range(5)
    )
    git_rule = css.index(".timesheet-day.source-git")
    chat_rule = css.index(".timesheet-day.source-chat")
    both_rule = css.index(".timesheet-day.source-both")

    assert "--evidence-git: #4f9a68" in css
    assert "--evidence-chat: #e59a4f" in css
    assert git_rule > intensity_rule
    assert chat_rule > intensity_rule
    assert both_rule > intensity_rule
    assert "background: var(--evidence-git)" in _rule(
        css, ".timesheet-day.source-git"
    )
    assert "background: var(--evidence-chat)" in _rule(
        css, ".timesheet-day.source-chat"
    )
    mixed_rule = _rule(css, ".timesheet-day.source-both")
    assert "background-image: linear-gradient" in mixed_rule
    assert "!important" in mixed_rule
    assert "var(--evidence-git)" in _rule(
        css, ".timesheet-source-legend .source-git"
    )
    assert "var(--evidence-chat)" in _rule(
        css, ".timesheet-source-legend .source-chat"
    )
    assert "var(--evidence-git)" in _rule(css, ".repository-evidence-git")
    assert "var(--evidence-chat)" in _rule(css, ".repository-evidence-chat")
