from __future__ import annotations

from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.review import build_review_queue, save_review


def test_review_queue_and_stable_categorisation(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        queue = build_review_queue(
            connection,
            settings,
            query="frobnicator failing",
            mode="lexical",
            limit=10,
        )
        assert queue
        item = queue[0]
        saved = save_review(
            connection,
            target_type=item["target_type"],
            target_key=item["target_key"],
            label="blind-spot",
            note="The same assumption was never checked.",
        )
        assert saved["label"] == "blind-spot"
        assert saved["review_state"] == "reviewed"

        remaining = build_review_queue(
            connection,
            settings,
            query="frobnicator failing",
            mode="lexical",
            limit=10,
        )
        assert all(candidate["target_key"] != item["target_key"] for candidate in remaining)
