from pathlib import Path

from tools.dev_api import _flatten_saved_record


REPO = Path(__file__).resolve().parents[1]
DEBATE_JS = REPO / "mmar" / "apps" / "debate" / "debate.js"
GALLERY_JS = REPO / "mmar" / "apps" / "debate" / "gallery.js"
GALLERY_HTML = REPO / "mmar" / "apps" / "debate" / "gallery.html"
DEBATE_CSS = REPO / "mmar" / "apps" / "debate" / "debate.css"


def test_battle_detail_never_renders_x_embed_html():
    js = DEBATE_JS.read_text(encoding="utf-8")
    assert "x_embed_html" not in js
    assert "result-x-embed" not in js
    assert "platform.x.com/widgets.js" not in js
    assert "twitter-tweet" not in js


def test_source_context_sections_stay_separate_in_detail():
    js = DEBATE_JS.read_text(encoding="utf-8")
    css = (REPO / "mmar" / "apps" / "debate" / "debate.css").read_text(encoding="utf-8")
    assert "contextLabel: \"追加情報\"" in js
    assert "battleContextCardsMarkup({ includeLabel: true })" in js
    assert "localized?.additional_info" in js
    assert "if (cards.length) return cards;" in js
    assert "${battleContextCardsMarkup({ includeLabel: true })}\n      ${nextStepCopy" in js
    assert "${battleContextCardsMarkup({ includeLabel: true })}\n  `;\n}" not in js
    assert "battle-output-right-copy-text" in js
    assert "result-source-evidence-copy" in js
    assert "battleCopy().fullSourceLabel || battleCopy().sourceLabel" in js
    assert "battle-output-right-copy-text\">${escapeHtml(battleSourceSummary)}</div>" in js
    assert "battle-output-right-copy-text\">${escapeHtml(summary)}</div>" not in js
    assert "battle-source-original" not in js
    text_rule = css[css.index(".battle-output-right-copy-text"):css.index(".battle-output-right-copy-ab")]
    assert "-webkit-line-clamp" not in text_rule
    assert "overflow: hidden" not in text_rule


def test_phase1_english_shell_does_not_require_localized_records():
    gallery_js = GALLERY_JS.read_text(encoding="utf-8")
    gallery_html = GALLERY_HTML.read_text(encoding="utf-8")
    debate_js = DEBATE_JS.read_text(encoding="utf-8")

    assert "Phase 1 viewer shell" in gallery_js
    assert "Phase 1 viewer shell" in gallery_html
    assert "record?.topic" in gallery_js
    assert "English preview not ready yet" not in gallery_js
    assert "fullSourceLabel: \"Full Source Text\"" in debate_js
    assert "battleCopy().fullSourceLabel || battleCopy().sourceLabel" in debate_js
    assert "contextLabel: \"Additional Info\"" in debate_js


def test_phase1_english_shell_sanitizes_object_source_text_and_buttons():
    html = (REPO / "mmar" / "apps" / "debate" / "debate.html").read_text(encoding="utf-8")
    js = DEBATE_JS.read_text(encoding="utf-8")

    assert "function readableSourceText" in js
    assert "\"source_text\"" in js
    assert "\"original_text\"" in js
    assert "\"description\"" in js
    assert "\"note\"" in js
    assert "\"value\"" in js
    assert "String(\n    localized?.summary" not in js
    assert "String(turn.a || \"\")" not in js
    assert "String(item.body || item.text" not in js
    assert "Back to edit" in html
    assert "Next battle" in html


def test_phase1_english_shell_uses_english_fallback_judgment_copy():
    js = DEBATE_JS.read_text(encoding="utf-8")

    assert "Generated English viewer-shell fallback." in js
    assert "The argument moved, but neither side fully closed the result." in js
    assert "Side B kept the weak point open and owned the decisive frame." in js
    assert "The key weak point surfaced here." in js


def test_combined_candidate_keeps_battle_layout_alignment_hooks():
    css = DEBATE_CSS.read_text(encoding="utf-8")

    assert "grid-template-columns: minmax(340px, 1fr) minmax(0, 1fr)" in css
    assert "aspect-ratio: 16 / 9" in css
    assert ".result-hero-media-block .battle-context-card" in css
    assert "body.battle-mode .summary-card-confidence" in css
    assert "border-radius: 999px" in css


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
