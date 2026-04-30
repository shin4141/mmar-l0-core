from tools.debate_core_v4 import _turn_prompt


def test_turn2_prompt_includes_both_side_context_preface():
    prompt = _turn_prompt(
        topic="この9歳の少年の反撃と父親のご褒美対応は正当か？",
        role="Affirmative",
        thesis="正当だ",
        anti_thesis="正当ではない",
        turn_name="turn2",
        opponent_last="相手は学校秩序を優先すべきだと述べた。",
        context_cards=[
            {"title": "殴られたか未遂か", "body": "実際に殴打があったのか、寸前で止まったのかで必要性評価は変わる。"},
            {"title": "繰り返し暴力の関係性", "body": "単発の衝突か、継続的ないじめかで比例性判断は変わる。"},
        ],
    )

    assert "Turn 2 Context Cards:" in prompt
    assert "Before rebutting, read the opponent's Turn 1 through this context." in prompt
    assert "Use any context that helps weaken the opponent's premise." in prompt
    assert "Do not force weak context." in prompt
    assert "Your goal is to win the rebuttal, not to summarize the context." in prompt
    assert "Opponent latest turn:" in prompt


def test_turn1_prompt_does_not_include_context_preface():
    prompt = _turn_prompt(
        topic="この9歳の少年の反撃と父親のご褒美対応は正当か？",
        role="Affirmative",
        thesis="正当だ",
        anti_thesis="正当ではない",
        turn_name="turn1",
        context_cards=[{"title": "殴られたか未遂か", "body": "必要性評価が変わる。"}],
    )

    assert "Turn 2 Context Cards:" not in prompt
