from pathlib import Path

from tools.dev_api import _flatten_saved_record


REPO = Path(__file__).resolve().parents[1]
DEBATE_JS = REPO / "mmar" / "apps" / "debate" / "debate.js"


def test_battle_detail_never_renders_x_embed_html():
    js = DEBATE_JS.read_text(encoding="utf-8")
    assert "x_embed_html" not in js
    assert "result-x-embed" not in js
    assert "platform.x.com/widgets.js" not in js
    assert "twitter-tweet" not in js


def test_source_context_sections_stay_separate_in_detail():
    js = DEBATE_JS.read_text(encoding="utf-8")
    assert "contextLabel: \"追加情報\"" in js
    assert "battle-source-original" in js
    assert "battleContextCardsMarkup({ includeLabel: true })" in js
    assert "battle-output-right-copy-text" in js
    assert "battle-output-right-copy-text\">${escapeHtml(summary)}</div>\n      ${abCopy" in js


def test_flatten_preserves_context_cards_from_nested_debate_result():
    record = {
        "session_id": "run_context",
        "run_json": {
            "debate_result": {
                "topic": "topic",
                "stance_a": "A",
                "stance_b": "B",
                "context_card_mode": "v1",
                "context_cards": [{"title": "追加", "body": "後から入った条件"}],
                "transcript_json": [{"turn": 1, "a": "A1", "b": "B1"}],
            }
        },
    }

    flattened = _flatten_saved_record(record, curated=True)

    assert flattened["context_card_mode"] == "v1"
    assert flattened["context_cards"] == [{"title": "追加", "body": "後から入った条件"}]
