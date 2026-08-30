from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def test_service_templates_are_portable_and_do_not_embed_secrets() -> None:
    templates = list((REPO_ROOT / "deploy").rglob("*.in"))
    assert templates
    combined = "\n".join(path.read_text(encoding="utf-8") for path in templates)
    assert "@REPO_ROOT@" in combined
    assert "/home/" not in combined
    assert "postgresql://" not in combined
    assert "CHATREVIEW_DATABASE_URL=" not in combined
