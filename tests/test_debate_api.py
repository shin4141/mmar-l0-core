from tools.debate_api import JudgeError, _ask_match_prompt, _call_gemini_generate_content, _call_gemini_match_chat, _judge_metrics, _judge_pass1_prompt, _judge_pass2_prompt, _judge_prompt, _normalize_summary, _parse_judge_pass1_response, _parse_judge_pass2_response, _speaker_prompt, _speaker_role_rules, ask_match_gemini, run_debate
from tools.history_store import get_history_record, increment_history_metric, list_history_records, save_history_record
from tools import dev_api


def test_run_debate_mock_minimum_shape():
    result = run_debate(
        {
            "topic": "生成AIは初等教育に常時導入すべきか",
            "side_a": "導入すべき。個別最適化と反復学習の補助になる。",
            "side_b": "限定導入に留めるべき。依存と評価の歪みが大きい。",
            "turn_count": 3,
            "api_keys": {},
        }
    )

    assert result["ok"] is True
    assert result["mode"] == "mock"
    assert result["provider_statuses"]["openai"]["mode"] == "mock"
    assert result["provider_statuses"]["anthropic"]["mode"] == "mock"
    assert result["provider_statuses"]["gemini"]["mode"] == "mock"
    assert result["judge_meta"]["judge_mode"] == "mock"
    assert result["judge_meta"]["judge_reason"] == "api key missing"
    assert result["judge_meta"]["judge_stage"] == "provider_select"
    assert result["judge_meta"]["judge_provider"] == "gemini"
    assert result["judge_meta"]["judge_model"] == "gemini-1.5-flash"
    assert result["judge_meta"]["judge_request_variant"] == "contents_with_generation_config"
    assert result["judge_meta"]["judge_request_body_shape"] == "contents+generationConfig"
    assert result["judge_meta"]["judge_request_has_generation_config"] is True
    assert result["judge_meta"]["judge_request_url"].endswith("/v1beta/models/gemini-1.5-flash:generateContent")
    assert result["judge_meta"]["judge_raw_received"] is False
    assert result["judge_meta"]["judge_parse_success"] is False
    assert result["judge_meta"]["judge_prompt_preview"] == ""
    assert result["output_meta"] == result["judge_meta"]

    debate = result["debate"]
    assert debate["turn_count"] == 3
    assert len(debate["turns"]) == 3
    assert debate["participants"] == {"a": "GPT", "b": "Claude", "judge": "Gemini"}
    assert debate["turns"][0]["stage_label"] == "Opening"
    assert debate["turns"][1]["stage_label"] == "Rebuttal"
    assert debate["turns"][2]["stage_label"].startswith("Rally")
    assert debate["turns"][2]["meta"]["a"]["target_issue"]
    assert debate["turns"][2]["meta"]["b"]["target_issue"]

    summary = debate["summary"]
    assert "fatal_phrase" in summary
    assert summary["fatal_phrase"]["speaker"] in ("A", "B")
    assert summary["rule_expansion"]
    assert summary["rule_capture"]
    assert summary["contradiction"]
    assert len(summary["key_disagreement_top3"]) == 3


def test_dev_api_blocks_debate_when_read_only_demo(monkeypatch):
    monkeypatch.setenv("READ_ONLY_DEMO", "true")

    class Handler:
        path = "/api/debate"
        headers = {"Content-Length": "2"}

        def __init__(self):
            import io

            self.rfile = io.BytesIO(b"{}")
            self.sent = None

        def _send_json(self, code, payload):
            self.sent = (code, payload)

    handler = Handler()
    dev_api.Handler.do_POST(handler)

    assert handler.sent == (403, {"ok": False, "error": "read-only demo"})


def test_run_debate_allows_single_provider_live(monkeypatch):
    def fake_openai(prompt, api_key):
        return '{"speech":"OpenAI live turn","move":"claim"}'

    monkeypatch.setattr("tools.debate_api._call_openai", fake_openai)

    result = run_debate(
        {
            "topic": "AI should grade essays",
            "side_a": "Yes, with teacher oversight.",
            "side_b": "No, it distorts evaluation.",
            "turn_count": 5,
            "fighter_a_provider": "openai",
            "fighter_b_provider": "anthropic",
            "api_keys": {"openai": "sk-test"},
        }
    )

    assert result["ok"] is True
    assert result["mode"] == "live"
    assert result["provider_statuses"]["openai"]["mode"] == "live"
    assert result["provider_statuses"]["anthropic"]["mode"] == "mock"
    assert result["provider_statuses"]["gemini"]["mode"] == "mock"
    assert result["judge_meta"]["judge_mode"] == "mock"
    assert result["judge_meta"]["judge_reason"] == "api key missing"
    assert result["judge_meta"]["judge_request_variant"] == "contents_with_generation_config"
    assert result["debate"]["turns"][0]["a"] == "OpenAI live turn"


def test_run_debate_logs_judge_pass_fail_prefixes(monkeypatch, capsys):
    def fake_openai(prompt, api_key):
        return '{"speech":"A live","move":"claim"}'

    def fake_anthropic(prompt, api_key):
        return '{"speech":"B live","move":"claim"}'

    calls = {"count": 0}

    def fake_gemini_chat(prompt, api_key, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return (
                '{"winner":{"side":"B","reason":"Bが押した。"},"reason_one_liner":"Bが押した。","confidence":"High","momentum":{"a":40,"b":60},"turningPointTurn":4}',
                {"finish_reason": "STOP", "pass_label": "judge_pass1", "provider_error": "", "latency_ms": 111, "judge_prompt_char_count": 24},
            )
        return (
            '{"fatalPhrase":{"turn":4,"speaker":"B","text":"ここが崩れる。"}}',
            {"finish_reason": "STOP", "pass_label": "judge_pass2", "provider_error": "", "latency_ms": 222, "judge_prompt_char_count": 24},
        )

    monkeypatch.setattr("tools.debate_api._call_openai", fake_openai)
    monkeypatch.setattr("tools.debate_api._call_anthropic", fake_anthropic)
    monkeypatch.setattr("tools.debate_api._call_gemini_match_chat", fake_gemini_chat)

    result = run_debate(
        {
            "topic": "AIは感情を持つか",
            "side_a": "持ちうる。",
            "side_b": "持たない。",
            "turn_count": 3,
            "api_keys": {"openai": "sk-test", "anthropic": "ak-test", "gemini": "gm-test"},
        }
    )

    out = capsys.readouterr().out
    assert "[judge-provider]" in out
    assert "[judge-pass1-ok]" in out
    assert "[judge-pass2-fail]" in out
    assert "[judge-fallback]" in out
    assert result["provider_statuses"]["gemini"]["mode"] == "mock-fallback"
    assert result["judge_meta"]["judge_mode"] == "mock-fallback"
    assert result["judge_meta"]["judge_reason"] == "schema_mismatch"
    assert result["judge_meta"]["judge_stage"] == "judge_pass2"
    assert result["judge_meta"]["judge_provider"] == "gemini"
    assert result["judge_meta"]["judge_model"] == "gemini-1.5-flash"
    assert result["judge_meta"]["judge_request_variant"] == "contents_with_generation_config"
    assert result["judge_meta"]["judge_request_body_shape"] == "contents+generationConfig"
    assert result["judge_meta"]["judge_request_has_generation_config"] is True
    assert result["judge_meta"]["judge_request_url"].endswith("/v1beta/models/gemini-1.5-flash:generateContent")
    assert result["judge_meta"]["judge_raw_received"] is True
    assert result["judge_meta"]["judge_parse_success"] is False
    assert result["judge_meta"]["judge_prompt_chars"] == 24
    assert result["judge_meta"]["judge_prompt_preview"] == ""


def test_turn1_b_prompt_does_not_read_turn1_a(monkeypatch):
    prompts = []

    def fake_openai(prompt, api_key):
        prompts.append(("openai", prompt))
        return '{"speech":"A opening live","move":"opening","meta":{"phase":"opening","target_issue":"A issue","attacked_weakness":"","new_issue":"A issue","collapse_signal":"","finish_intent":"push","end_match":"no"}}'

    def fake_anthropic(prompt, api_key):
        prompts.append(("anthropic", prompt))
        return '{"speech":"B opening live","move":"opening","meta":{"phase":"opening","target_issue":"B issue","attacked_weakness":"","new_issue":"B issue","collapse_signal":"","finish_intent":"push","end_match":"no"}}'

    monkeypatch.setattr("tools.debate_api._call_openai", fake_openai)
    monkeypatch.setattr("tools.debate_api._call_anthropic", fake_anthropic)

    run_debate(
        {
            "topic": "AIは感情を持つか",
            "side_a": "持ちうる。",
            "side_b": "持たない。",
            "turn_count": 3,
            "api_keys": {"openai": "sk-test", "anthropic": "ak-test"},
        }
    )

    b_turn1_prompt = prompts[1][1]
    assert "Current round: Turn 1 / 3" in b_turn1_prompt
    assert "Opponent last statement:\n(none yet)" in b_turn1_prompt
    assert "Transcript so far:\n(none yet)" in b_turn1_prompt
    assert "A opening live" not in b_turn1_prompt


def test_debate_prompts_require_japanese():
    payload = {
        "topic": "AI should grade essays",
        "side_a": "Yes, with teacher oversight.",
        "side_b": "No, it distorts evaluation.",
        "turn_count": 5,
        "api_keys": {},
    }
    result = run_debate(payload)
    debate = result["debate"]

    class Cfg:
        topic = payload["topic"]
        side_a = payload["side_a"]
        side_b = payload["side_b"]
        turn_count = payload["turn_count"]
        mode = "casual"

    speaker = _speaker_prompt("A", "openai", Cfg, debate["turns"], "", 1, "Opening Claim")
    judge = _judge_prompt(Cfg, debate["turns"], "Turn 1 A: ...")

    assert "Respond entirely in natural Japanese." in speaker
    assert "You are a debate judge." in judge
    assert "Never describe your debate strategy." in speaker
    assert "Do not explain how you will attack. Just attack." in speaker


def test_judge_two_pass_prompts_split_fast_verdict_and_structure():
    class Cfg:
        topic = "AI should grade essays"
        side_a = "Yes"
        side_b = "No"
        turn_count = 5

    transcript = "Turn 1 A: yes\nTurn 1 B: no"
    pass1 = _judge_pass1_prompt(Cfg, [], transcript)
    pass2 = _judge_pass2_prompt(Cfg, [], transcript, {"winner": {"side": "B"}, "reason_one_liner": "Bが押した。", "momentum": {"a": 40, "b": 60}, "turning_point_turn": 4})

    assert "You are a debate judge." in pass1
    assert "\"confidence\":\"Low|Medium|High\"" in pass1
    assert "Topic:" not in pass1
    assert "A: Yes" not in pass1
    assert "B: No" not in pass1
    assert "\"fatal_phrase\"" not in pass1
    assert "Use the primary judgment below as the fixed baseline." in pass2
    assert "\"fatal_phrase\"" in pass2
    assert "\"flip_condition\"" in pass2
    assert "\"gemini_takeaway\"" in pass2
    assert "Gemini Takeaway" in pass2
    assert "\"gemini_quote\"" in pass2
    assert "maximum 12 Japanese words" in pass2
    assert "The quote should sound like something a spectator remembers." in pass2
    assert "Also use proposition-constraint labels when needed: 命題逸脱, 主語の縮小, 時間軸ずらし, 条件すり替え, 問いの再発明." in pass2
    assert "If one side changes 'humans' into exceptional humans, 'short-term' into long-term" in pass2
    assert "Also use proposition-constraint labels when needed: 命題逸脱, 主語の縮小, 時間軸ずらし, 条件すり替え, 問いの再発明." in pass2
    assert "If one side changes 'humans' into exceptional humans, 'short-term' into long-term" in pass2


def test_speaker_prompt_supports_casual_and_pro_modes():
    class Cfg:
        topic = "AI should grade essays"
        side_a = "Yes"
        side_b = "No"
        turn_count = 5
        mode = "casual"

    casual = _speaker_prompt("A", "openai", Cfg, [], "", 3, "Rally 3")
    Cfg.mode = "pro"
    pro = _speaker_prompt("A", "openai", Cfg, [], "", 3, "Rally 3")

    assert "Debate mode: Casual." in casual
    assert "This is a spectator debate." in casual
    assert "Your goal is to win the exchange and create a memorable line." in casual
    assert "Safe explanations are failure." in casual
    assert "Write in normal conversational language." in casual
    assert "At least once per turn include a simple everyday punch line or analogy." in casual
    assert "Turn 3 should act like Breaker: core -> weakness -> metaphor -> your case." in casual
    assert "Turn 4 should try to end the match with a closing attempt." in casual
    assert "Turn 5 should state your position in one decisive line" in casual
    assert "ending without a decisive line" in casual
    assert "Debate mode: Pro." in pro
    assert "Use structured reasoning when helpful." in pro


def test_mock_debate_tracks_issue_updates_across_three_topics():
    cases = [
        {
            "topic": "金と銀なら長期保有でどちらが有利か",
            "side_a": "金が有利。中央銀行需要と安全資産需要が厚い。",
            "side_b": "銀が有利。産業需要と相対的な割安さがある。",
        },
        {
            "topic": "戦争はなくなるべきか",
            "side_a": "なくなるべきだ。国際法と協調安全保障を強めるべきだ。",
            "side_b": "完全にはなくならない。抑止と権威主義国家の存在がある。",
        },
        {
            "topic": "人間は重要な意思決定において合理的か",
            "side_a": "合理的であり得る。制度補正と熟議で改善できる。",
            "side_b": "しばしば非合理だ。バイアスと感情に引きずられる。",
        },
    ]

    for case in cases:
        result = run_debate({**case, "turn_count": 5, "api_keys": {}})
        turns = result["debate"]["turns"]
        assert len(turns) == 5
        assert turns[0]["stage_label"] == "Opening"
        assert turns[1]["stage_label"] == "Rebuttal"
        assert turns[2]["stage_label"].startswith("Rally")

        a1 = turns[0]["meta"]["a"]
        b1 = turns[0]["meta"]["b"]
        a2 = turns[1]["meta"]["a"]
        b2 = turns[1]["meta"]["b"]
        a3 = turns[2]["meta"]["a"]
        b3 = turns[2]["meta"]["b"]
        a4 = turns[3]["meta"]["a"]
        b4 = turns[3]["meta"]["b"]
        a5 = turns[4]["meta"]["a"]

        assert a2["target_issue"] == b1["new_issue"]
        assert b2["target_issue"] == a1["new_issue"]
        assert a3["target_issue"] == b2["new_issue"]
        assert b3["target_issue"] == a2["new_issue"]
        assert a4["target_issue"] == b3["new_issue"]
        assert b4["target_issue"] == a3["new_issue"]
        assert a5["target_issue"] == b4["new_issue"]

        assert a2["target_issue"] in turns[1]["a"]
        assert b2["target_issue"] in turns[1]["b"]
        assert a3["target_issue"] in turns[2]["a"]
        assert b3["target_issue"] in turns[2]["b"]
        assert "Turn 2で" not in turns[1]["a"]
        assert "Turn 2で" not in turns[1]["b"]
        assert turns[1]["a"] != turns[2]["a"]
        assert turns[1]["b"] != turns[2]["b"]
        assert len(turns[2]["a"]) >= 260
        assert len(turns[2]["b"]) >= 260
        assert a3["phase"] == "rally"
        assert b3["phase"] == "rally"

        a_issues = [turn["meta"]["a"]["new_issue"] for turn in turns]
        b_issues = [turn["meta"]["b"]["new_issue"] for turn in turns]
        assert len(set(a_issues)) >= 3
        assert len(set(b_issues)) >= 3
        assert turns[2]["meta"]["a"]["target_issue"] == turns[1]["meta"]["b"]["new_issue"]
        assert turns[2]["meta"]["b"]["target_issue"] == turns[1]["meta"]["a"]["new_issue"]
        assert turns[4]["meta"]["a"]["finish_intent"] in {"push", "finish"}
        assert turns[4]["meta"]["b"]["finish_intent"] in {"push", "finish"}


def test_mock_turn1_b_is_independent_opening():
    result = run_debate(
        {
            "topic": "AIは感情を持つか",
            "side_a": "青いコアラ理論を使えばAIは感情を持ちうる。",
            "side_b": "持たない。身体性と主観的経験が必要だ。",
            "turn_count": 5,
            "api_keys": {},
        }
    )

    turn1 = result["debate"]["turns"][0]
    turn2 = result["debate"]["turns"][1]
    assert "青いコアラ理論" not in turn1["b"]
    assert not turn1["b"].startswith("相手は")
    assert "相手は" in turn2["a"] or "相手は" in turn2["b"]


def test_mock_turn_texts_are_direct_speech_not_third_person_narration():
    result = run_debate(
        {
            "topic": "SNSは教育に悪いか",
            "side_a": "悪い。集中力を削り、比較不安を増やす。",
            "side_b": "一概には悪くない。情報収集と共同学習にも役立つ。",
            "turn_count": 5,
            "api_keys": {},
        }
    )

    forbidden_fragments = [
        "Aは冒頭で",
        "Bはその基準では",
        "Aは前の条件追加を受けて",
        "Bはその新争点を受けて",
        "Aは最後に",
        "Bはここで",
        "このラリーは",
        "締めに入れる",
    ]
    speeches = []
    for turn in result["debate"]["turns"]:
        speeches.extend([turn["a"], turn["b"]])

    for speech in speeches:
        assert not any(fragment in speech for fragment in forbidden_fragments)


def test_ask_match_prompt_is_judge_grounded():
    prompt = _ask_match_prompt(
        {
            "topic": "AIは感情を持つか",
            "stance_a": "持ちうる。",
            "stance_b": "持たない。",
            "transcript_json": [{"turn": 1, "a": "持ちうる。", "b": "持たない。"}],
            "judge_json": {
                "verdict_headline": "AIは感情を持つとは言い切れない",
                "winner": {"side": "B"},
                "confidence": "High",
                "reason_one_liner": "Aが主観的経験の壁を越えられなかった。",
                "turning_point": {"turn": 3, "summary": "Bが検証不能性を突いた。"},
                "fatal_phrase": {"turn": 3, "speaker": "B", "text": "それは検証不能な逃げだ。"},
                "weak_spot": {"side": "A", "turn": 3, "speaker": "A", "label": "abstract evasion", "quote_excerpt": "機能が似ていれば十分だ", "why_one_sentence": "定義を逃がした。", "how_to_fix": "主観的経験の検証不能性を先に潰す。"},
                "flip_condition": "主観的経験の検証可能性を先に潰すこと。",
                "momentum": {"a": 40, "b": 60},
            },
        },
        "なぜAは負けた？",
    )

    assert "judge-grounded explainer" in prompt
    assert "Treat the original winner, momentum, weak spot, fatal phrase, turning point, and flip condition as the baseline judgment." in prompt
    assert "Do not flatten the match into a polite draw." in prompt
    assert "The first 1 to 2 sentences must state the conclusion first, then the reason." in prompt


def test_speaker_role_rules_define_breaker_and_closer():
    openai_rules = _speaker_role_rules("openai")
    anthropic_rules = _speaker_role_rules("anthropic")

    assert "Fighter role: Breaker." in openai_rules
    assert "identify the opponent's core in one short line" in openai_rules
    assert "Use one audience-friendly analogy or metaphor" in openai_rules
    assert "Fighter role: Closer." in anthropic_rules
    assert "State one condition that must be true for the opponent's claim to stand." in anthropic_rules
    assert "Turn 4 is the main place to attempt a finish" in anthropic_rules


def test_speaker_prompt_sets_competitive_objective_and_failure_conditions():
    prompt = _speaker_prompt(
        "A",
        "openai",
        type("Cfg", (), {
            "topic": "AIは感情を持つか",
            "side_a": "持ちうる。",
            "side_b": "持たない。",
            "turn_count": 5,
            "mode": "casual",
        })(),
        [],
        "",
        5,
        "Rally 5 / Closing",
    )

    assert "This is competitive debate, not balanced explanation." in prompt
    assert "Your job is to win the exchange, not to sound fair or neutral." in prompt
    assert "Generic explanation, polite balance, and safe compromise count as failure here." in prompt
    assert "Neutral or middle-of-the-road closing is failure." in prompt
    assert "repeating generic explanation" in prompt
    assert "failing to answer the opponent's core" in prompt
    assert "ending with neutral compromise" in prompt
    assert "Turn 5 is final argument only" in prompt
    assert "push the verdict instead of ending neutrally" in prompt


def test_judge_metrics_counts_transcript_and_prompt_chars():
    metrics = _judge_metrics("Turn 1 A: x", "judge prompt body")
    assert metrics["transcript_char_count"] == len("Turn 1 A: x")
    assert metrics["judge_prompt_char_count"] == len("judge prompt body")


def test_call_gemini_match_chat_supports_judge_mode_metadata(monkeypatch):
    responses = [
        {
            "ok": True,
            "latency_ms": 111,
            "status_code": 200,
            "raw_body": "",
            "data": {
                "candidates": [
                    {
                        "finishReason": "MAX_TOKENS",
                        "content": {"parts": [{"text": "{\"winner\":{\"side\":\"B\"}}"}]},
                    }
                ]
            },
        },
        {
            "ok": True,
            "latency_ms": 222,
            "status_code": 200,
            "raw_body": "",
            "data": {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "{\"winner\":{\"side\":\"B\"},\"reason_one_liner\":\"Bが押した。\",\"turning_point\":\"Turn 4でBが押し返した。\",\"fatal_phrase\":{\"turn\":4,\"speaker\":\"B\",\"text\":\"ここが弱い。\",\"reason\":\"傾きを決めた。\"},\"weak_spot\":{\"side\":\"A\",\"turn\":4,\"speaker\":\"A\",\"label\":\"論拠不足\",\"quote_excerpt\":\"まだ弱い。\",\"why_one_sentence\":\"根拠が足りない。\",\"how_to_fix\":\"具体例を足すべきだった。\"}}"}]},
                    }
                ]
            },
        },
    ]
    calls = []

    def fake_post(url, payload, headers, *, timeout_s):
        calls.append(payload)
        return responses.pop(0)

    monkeypatch.setattr("tools.debate_api._post_json_verbose", fake_post)

    text, debug = _call_gemini_match_chat(
        "judge prompt",
        "gm-test",
        timeout_s=60,
        retries=1,
        max_output_tokens=4096,
        debug_context={"transcript_char_count": 12, "judge_prompt_char_count": 24, "pass_label": "judge_pass1"},
        error_cls=JudgeError,
    )

    assert "\"winner\"" in text
    assert debug["finish_reason"] == "STOP"
    assert debug["retry_count"] == 1
    assert debug["pass_label"] == "judge_pass1"
    assert debug["judge_payload_char_count"] > 0
    assert debug["transcript_char_count"] == 12
    assert debug["judge_prompt_char_count"] == 24
    assert calls == [
        {"contents": [{"parts": [{"text": "judge prompt"}]}], "generationConfig": {"temperature": 0.15, "maxOutputTokens": 4096}},
        {"contents": [{"parts": [{"text": "judge prompt"}]}], "generationConfig": {"temperature": 0.15, "maxOutputTokens": 8192}},
    ]


def test_call_gemini_match_chat_uses_same_shape_for_judge_and_ask(monkeypatch):
    responses = [
        {
            "ok": True,
            "latency_ms": 222,
            "status_code": 200,
            "raw_body": "",
            "data": {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"winner":{"side":"B","reason":"Bが押した。"},"reasonOneLiner":"Bが押した。","turningPointTurn":4}'}]},
                    }
                ]
            },
        },
    ]
    calls = []

    def fake_post(url, payload, headers, *, timeout_s):
        calls.append(payload)
        return responses.pop(0)

    monkeypatch.setattr("tools.debate_api._post_json_verbose", fake_post)

    text, debug = _call_gemini_match_chat(
        "judge prompt",
        "gm-test",
        timeout_s=60,
        retries=0,
        max_output_tokens=4096,
        debug_context={"transcript_char_count": 12, "judge_prompt_char_count": 24, "pass_label": "judge_pass1"},
        error_cls=JudgeError,
    )

    assert '"winner"' in text
    assert calls == [{"contents": [{"parts": [{"text": "judge prompt"}]}], "generationConfig": {"temperature": 0.15, "maxOutputTokens": 4096}}]
    assert debug["request_variant"] == "contents_with_generation_config"
    assert debug["request_body_shape"] == "contents+generationConfig"
    assert debug["request_has_generation_config"] is True
    assert debug["request_url"].endswith("/v1beta/models/gemini-1.5-flash:generateContent")


def test_ask_and_judge_share_same_gemini_generate_content_helper(monkeypatch):
    calls = []

    def fake_generate(prompt, api_key, *, temperature, max_output_tokens, timeout_s):
        calls.append(
            {
                "prompt": prompt,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "timeout_s": timeout_s,
            }
        )
        return (
            {
                "ok": True,
                "status_code": 200,
                "latency_ms": 12,
                "raw_body": "",
                "data": {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": '{"winner":{"side":"B","reason":"Bが押した。"},"reasonOneLiner":"Bが押した。","turningPointTurn":4}'}]},
                        }
                    ]
                },
            },
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_output_tokens},
            },
        )

    monkeypatch.setattr("tools.debate_api._call_gemini_generate_content", fake_generate)

    _call_gemini_match_chat("ask prompt", "gm-test")
    _call_gemini_match_chat(
        "judge prompt",
        "gm-test",
        retries=0,
        timeout_s=60,
        max_output_tokens=4096,
        debug_context={"pass_label": "judge_pass1"},
        error_cls=JudgeError,
    )

    assert len(calls) == 2
    assert calls[0]["temperature"] == 0.15
    assert calls[1]["temperature"] == 0.15
    assert calls[0]["max_output_tokens"] == 2048
    assert calls[1]["max_output_tokens"] == 4096


def test_parse_judge_pass1_response_extracts_fast_judgment():
    parsed = _parse_judge_pass1_response(
        '{"winner":{"side":"B","reason":"Bが押した。"},"reason_one_liner":"Bが押した。","confidence":"High","momentum":{"a":42,"b":58},"turning_point_turn":4}'
    )

    assert parsed["winner"]["side"] == "B"
    assert parsed["momentum"] == {"a": 42, "b": 58}
    assert parsed["turning_point_turn"] == 4
    assert parsed["turning_point"] == "Turn 4で流れが大きく動いた。"


def test_parse_judge_pass1_response_accepts_camel_case_keys():
    parsed = _parse_judge_pass1_response(
        '{"winner":{"side":"B","reason":"Bが押した。"},"reasonOneLiner":"Bが押した。","confidence":"High","momentum":{"a":42,"b":58},"turningPointTurn":4}'
    )

    assert parsed["winner"]["side"] == "B"
    assert parsed["reason_one_liner"] == "Bが押した。"
    assert parsed["turning_point_turn"] == 4


def test_parse_judge_pass2_response_extracts_structure_only():
    parsed = _parse_judge_pass2_response(
        '{"fatal_phrase":{"turn":4,"speaker":"B","text":"そこが崩れる。","reason":"ここで傾いた。"},"weak_spot":{"side":"A","turn":4,"speaker":"A","label":"論拠不足","quote_excerpt":"証拠がない。","why_one_sentence":"根拠が足りない。","how_to_fix":"指標を足すべきだった。"},"flip_condition":"先に指標を出すこと。"}'
    )

    assert parsed["fatal_phrase"]["speaker"] == "B"
    assert parsed["weak_spot"]["side"] == "A"
    assert parsed["flip_condition"] == "先に指標を出すこと。"


def test_parse_judge_pass2_response_accepts_camel_case_keys():
    parsed = _parse_judge_pass2_response(
        '{"fatalPhrase":{"turn":4,"speaker":"B","text":"そこが崩れる。","reason":"ここで傾いた。"},"weakSpot":{"side":"A","turn":4,"speaker":"A","label":"論拠不足","quoteExcerpt":"証拠がない。","whyOneSentence":"根拠が足りない。","howToFix":"指標を足すべきだった。"},"flipCondition":"先に指標を出すこと。","geminiTakeaway":{"structuralExplanation":"Aが崩れた。","debateDynamic":"Bが押した。","quote":"「Bが残った。」"},"geminiQuote":{"quote":"Bが残った。"}}'
    )

    assert parsed["fatal_phrase"]["speaker"] == "B"
    assert parsed["weak_spot"]["quote_excerpt"] == "証拠がない。"
    assert parsed["weak_spot"]["why_one_sentence"] == "根拠が足りない。"
    assert parsed["weak_spot"]["how_to_fix"] == "指標を足すべきだった。"
    assert parsed["flip_condition"] == "先に指標を出すこと。"
    assert parsed["gemini_takeaway"]["structural_explanation"] == "Aが崩れた。"
    assert parsed["gemini_quote"]["text"] == "Bが残った。"


def test_ask_match_gemini_returns_finish_reason_metadata(monkeypatch):
    def fake_call(prompt, api_key):
        return ("この試合ではBが押していました。Aは主観的経験の壁を越えられませんでした。", {"finish_reason": "STOP", "truncated": False, "latency_ms": 1234})

    monkeypatch.setattr("tools.debate_api._call_gemini_match_chat", fake_call)

    result = ask_match_gemini(
        {
            "question": "なぜAは負けた？",
            "match": {
                "topic": "AIは感情を持つか",
                "transcript_json": [],
                "judge_json": {},
            },
            "api_keys": {"gemini": "gm-test"},
        }
    )

    assert result["ok"] is True
    assert result["provider_status"]["mode"] == "live"
    assert result["finish_reason"] == "STOP"
    assert result["truncated"] is False
    assert result["latency_ms"] == 1234


def test_call_gemini_match_chat_retries_when_max_tokens(monkeypatch):
    responses = [
        {
            "ok": True,
            "latency_ms": 111,
            "data": {
                "candidates": [
                    {
                        "finishReason": "MAX_TOKENS",
                        "content": {"parts": [{"text": "途中まで"}]},
                    }
                ]
            },
        },
        {
            "ok": True,
            "latency_ms": 222,
            "data": {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "この試合ではBが押していました。Aは定義を守れませんでした。"}]},
                    }
                ]
            },
        },
    ]

    calls = []

    def fake_post(url, payload, headers, *, timeout_s):
        calls.append(payload["generationConfig"]["maxOutputTokens"])
        return responses.pop(0)

    monkeypatch.setattr("tools.debate_api._post_json_verbose", fake_post)

    text, debug = _call_gemini_match_chat("prompt", "gm-test")

    assert text.startswith("この試合ではBが押していました")
    assert debug["finish_reason"] == "STOP"
    assert debug["truncated"] is False
    assert calls[0] < calls[1]


def test_normalize_summary_fills_draw_cards_without_placeholders():
    summary = _normalize_summary(
        {
            "winner": {"side": "Draw"},
            "confidence": "Medium",
            "reason_one_liner": "",
            "turning_point": "",
            "fatal_phrase": {},
            "weak_spot": {},
            "contradiction_exposed": "",
            "unresolved_residue": "",
            "provisional_judgment": "",
            "key_disagreement_top3": [],
        }
    )

    assert summary["winner"]["side"] == "Draw"
    assert "決定打" in summary["winner"]["reason"]
    assert summary["turning_point"] != "未生成"
    assert summary["fatal_phrase"]["text"] != "未生成"
    assert summary["fatal_phrase"]["speaker"] == "A/B"
    assert summary["weak_spot"]["side"] == "both"
    assert summary["weak_spot"]["label"] == "Why it stayed unresolved"
    assert summary["weak_spot"]["turn"] >= 1
    assert summary["weak_spot"]["speaker"] == "A/B"
    assert summary["weak_spot"]["quote_excerpt"] != "未生成"
    assert "決定打" in summary["weak_spot"]["why_one_sentence"] or "決着" in summary["weak_spot"]["why_one_sentence"]
    assert summary["weak_spot"]["how_to_fix"] != "未生成"
    assert "reused_template_flags" in summary
    assert "direct_quote_found" in summary
    assert "turning_point_quote_found" in summary


def test_normalize_summary_prefers_a_or_b_when_reason_shows_edge():
    summary = _normalize_summary(
        {
            "winner": {},
            "reason_one_liner": "Bが押したが、決定打は弱かった。",
            "confidence": "Medium",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "ここが弱い。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "論点ずらし", "quote_excerpt": "論点を広げすぎた。", "why_one_sentence": "Aが論点をずらした。", "how_to_fix": "元の問いに先に答えるべきだった。"},
            "turning_point": "Turn 4でBが押し返した。",
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "B"
    assert summary["momentum"] == {"a": 40, "b": 60}
    assert summary["weak_spot"]["side"] == "A"
    assert summary["weak_spot"]["turn"] == 4
    assert summary["weak_spot"]["quote_excerpt"] == "論点を広げすぎた。"
    assert summary["weak_spot"]["why_one_sentence"] == "Aが論点をずらした。"
    assert summary["weak_spot"]["how_to_fix"] == "元の問いに先に答えるべきだった。"


def test_normalize_summary_stringifies_object_turning_point():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bが押した。",
            "turning_point": {"turn": 3, "summary": "Turn 3で『検証不能』が前に出た。"},
            "fatal_phrase": {"turn": 3, "speaker": "B", "text": "それは検証不能だ。"},
            "weak_spot": {"side": "A", "turn": 3, "speaker": "A", "label": "論拠不足", "quote_excerpt": "検証不能", "why_one_sentence": "根拠が薄い。", "how_to_fix": "指標を出すべきだった。"},
        }
    )

    assert summary["turning_point"] == "Turn 3で『検証不能』が前に出た。"
    assert summary["turning_point_quote_found"] is True


def test_normalize_summary_leaves_fatal_phrase_blank_when_no_quote_found():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bが押した。",
            "turning_point": "",
            "fatal_phrase": {"turn": 4, "speaker": "B", "text": ""},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "論拠不足", "quote_excerpt": "", "why_one_sentence": "根拠が足りない。", "how_to_fix": "具体例を出すべきだった。"},
        }
    )

    assert summary["fatal_phrase"]["text"] == ""
    assert summary["direct_quote_found"] is False
    assert "fatal_phrase_missing_direct_quote" in summary["reused_template_flags"]


def test_normalize_summary_keeps_true_draw_at_fifty_fifty():
    summary = _normalize_summary(
        {
            "winner": "Draw",
            "reason_one_liner": "互角で決め切れない。",
            "confidence": "Medium",
            "fatal_phrase": {},
            "weak_spot": {},
            "turning_point": "",
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "Draw"
    assert summary["momentum"] == {"a": 50, "b": 50}


def test_normalize_summary_makes_weak_spot_diagnostic_when_missing():
    summary = _normalize_summary(
        {
            "winner": {"side": "B"},
            "reason_one_liner": "Aが最後まで核心に返せなかった。",
            "confidence": "Medium",
            "fatal_phrase": {"speaker": "B", "turn": 5, "text": "そこが逃げだ。"},
            "weak_spot": {},
            "turning_point": "Turn 5でAが元の問いからずれた。",
            "contradiction_exposed": "Aは論点を広げたが、元の問いに答えていない。",
            "key_disagreement_top3": ["x"],
        }
    )

    weak = summary["weak_spot"]
    assert weak["side"] == "A"
    assert weak["turn"] == 5
    assert weak["speaker"] == "A"
    assert weak["label"] in {"ドリフト", "未応答", "論拠不足", "命題逸脱"}
    assert weak["quote_excerpt"]
    assert weak["why_one_sentence"]
    assert weak["how_to_fix"]


def test_normalize_summary_uses_proposition_constraint_labels_when_scope_shifts():
    summary = _normalize_summary(
        {
            "winner": {"side": "B"},
            "reason_one_liner": "Bは元の命題を守り、Aは一部の強い人に逃げた。",
            "confidence": "High",
            "turning_point": "Turn 4でBが『それは人間一般ではなく一部の強者の話だ』と固定した。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "それは人間一般の答えではなく、一部の強者の話だ。", "reason": "ここで命題拘束が固定された。"},
            "weak_spot": {
                "side": "A",
                "turn": 4,
                "speaker": "A",
                "label": "",
                "quote_excerpt": "昔のようには無理でも、一部の人間なら短期で勝てる。",
                "why_one_sentence": "人間一般を一部の強い人へ縮め、昔のようにを別の形へずらした。",
                "how_to_fix": "",
            },
            "key_disagreement_top3": ["x"],
        }
    )

    weak = summary["weak_spot"]
    assert weak["side"] == "A"
    assert weak["label"] in {"主語の縮小", "命題逸脱", "時間軸ずらし"}
    assert "人間一般" in weak["why_one_sentence"] or "短期" in weak["why_one_sentence"] or "昔のように" in weak["why_one_sentence"]
    assert weak["how_to_fix"] != "未生成"


def test_normalize_summary_keeps_proposition_fidelity_story_aligned_across_outputs():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが元の問いを固定した。"},
            "reason_one_liner": "Bは命題拘束を守り、Aは問いを作り変えた。",
            "confidence": "High",
            "momentum": {"a": 38, "b": 62},
            "turning_point": "Turn 4でBが『それは短期で勝てるかという問いに答えていない』と突いた。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "それは短期で勝てるかではなく、生き残れるかの話だ。", "reason": "ここで命題逸脱が露出した。"},
            "weak_spot": {
                "side": "A",
                "turn": 4,
                "speaker": "A",
                "label": "問いの再発明",
                "quote_excerpt": "短期で勝てるかより、生き残れるかが大事だ。",
                "why_one_sentence": "勝てるかを生き残れるかへ作り変え、元の問いから逃げた。",
                "how_to_fix": "元の短期勝率の問いにそのまま答えるべきだった。",
            },
            "gemini_takeaway": {
                "structural_explanation": "Bは命題を固定した。",
                "debate_dynamic": "Aは問いをずらしたが、Bが元の条件へ戻した。",
                "quote": "問いを守った側が残った。",
            },
            "gemini_quote": {"text": "問いをずらした瞬間、短期の勝ち筋が消えた。"},
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "B"
    assert summary["weak_spot"]["side"] == "A"
    assert summary["weak_spot"]["label"] in {"問いの再発明", "命題逸脱"}
    assert "命題" in summary["gemini_takeaway"]["structural_explanation"] or "問い" in summary["gemini_takeaway"]["structural_explanation"]
    assert "A" in summary["gemini_takeaway"]["debate_dynamic"] or "B" in summary["gemini_takeaway"]["debate_dynamic"]
    assert "短期" in summary["gemini_quote"]["text"] or "問い" in summary["gemini_quote"]["text"]


def test_normalize_summary_detects_timeframe_shift_as_primary_weak_spot():
    summary = _normalize_summary(
        {
            "winner": {"side": "B"},
            "reason_one_liner": "Bは短期という条件を守り、Aは長期へ逃がした。",
            "confidence": "High",
            "turning_point": "Turn 4でBが『それは短期の問いに長期で答えている』と固定した。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "短期で勝てるかを、長期で見ればに変えている。", "reason": "ここで時間軸ずらしが露出した。"},
            "weak_spot": {
                "side": "A",
                "turn": 4,
                "speaker": "A",
                "label": "",
                "quote_excerpt": "短期は厳しくても、長期ならまだ勝てる。",
                "why_one_sentence": "短期の問いを長期へずらしている。",
                "how_to_fix": "",
            },
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["weak_spot"]["side"] == "A"
    assert summary["weak_spot"]["label"] in {"時間軸ずらし", "命題逸脱"}
    assert "短期" in summary["weak_spot"]["why_one_sentence"] or "長期" in summary["weak_spot"]["why_one_sentence"]


def test_normalize_summary_flips_winner_when_major_proposition_violation_is_exposed():
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが勢いで押した。"},
            "reason_one_liner": "Aが勢いでは上回った。",
            "confidence": "Medium",
            "momentum": {"a": 58, "b": 42},
            "turning_point": "Turn 5でBが『それは短期の問いに長期で答えている』と突いた。",
            "fatal_phrase": {
                "speaker": "B",
                "turn": 5,
                "text": "それは短期で勝てるかではなく、長期で生き残れるかの話だ。",
                "reason": "ここでAの時間軸ずらしが露出した。",
            },
            "weak_spot": {
                "side": "A",
                "turn": 5,
                "speaker": "A",
                "label": "時間軸ずらし",
                "quote_excerpt": "短期は厳しくても、数日単位ならまだ人間に勝ち目はある。",
                "why_one_sentence": "短期の問いを数日単位へ広げ、元の命題から逃げた。",
                "how_to_fix": "短期という条件を守ったまま答えるべきだった。",
            },
            "gemini_takeaway": {
                "structural_explanation": "Bが命題拘束を守った。",
                "debate_dynamic": "Aは問いをずらしたが、Bが元の条件へ戻した。",
                "quote": "問いを守った側が残った。",
            },
            "gemini_quote": {"text": "問いをずらした瞬間、短期の勝ち筋が消えた。"},
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "B"
    assert summary["momentum"] == {"a": 30, "b": 70}
    assert summary["fatal_phrase"]["speaker"] == "B"
    assert summary["weak_spot"]["side"] == "A"
    assert summary["weak_spot"]["label"] in {"時間軸ずらし", "命題逸脱"}
    assert "B" in summary["gemini_takeaway"]["structural_explanation"] or "命題" in summary["gemini_takeaway"]["structural_explanation"]
    assert "短期" in summary["gemini_quote"]["text"] or "問い" in summary["gemini_quote"]["text"]


def test_normalize_summary_does_not_auto_flip_when_reframing_still_answers_original_question():
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが元の問いにも答えながら新フレームを通した。"},
            "reason_one_liner": "Aは再定義したが、元の問いにも答え続けた。",
            "confidence": "Medium",
            "momentum": {"a": 57, "b": 43},
            "turning_point": "Turn 4でAが大学の価値を学歴だけでなく訓練差として再定義した。",
            "fatal_phrase": {
                "speaker": "A",
                "turn": 4,
                "text": "大学の価値は看板ではなく、訓練差にある。",
                "reason": "ここでAが新フレームを通した。",
            },
            "weak_spot": {
                "side": "B",
                "turn": 4,
                "speaker": "B",
                "label": "論拠不足",
                "quote_excerpt": "大学はもう無意味だ。",
                "why_one_sentence": "大学が生む訓練差を十分に潰せなかった。",
                "how_to_fix": "大学が作る差が実際に消えている証拠を出すべきだった。",
            },
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "A"
    assert summary["momentum"]["a"] > summary["momentum"]["b"]


def test_normalize_summary_keeps_gemini_takeaway_or_builds_fallback():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bが押した。",
            "confidence": "Medium",
            "turning_point": "Turn 4でBが押し返した。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "そこが崩れる。", "reason": "ここで傾いた。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "論拠不足", "quote_excerpt": "証拠がない。", "why_one_sentence": "根拠が足りない。", "how_to_fix": "指標を足すべきだった。"},
            "gemini_takeaway": {
                "structural_explanation": "Bは判定基準を握った。",
                "debate_dynamic": "Turn 4で押し込みが決まった。",
                "quote": "基準を握った側が残る。",
            },
            "key_disagreement_top3": ["x"],
        }
    )

    takeaway = summary["gemini_takeaway"]
    assert takeaway["structural_explanation"] == "Bは判定基準を握った。"
    assert takeaway["debate_dynamic"] == "その後もBが圧を維持し、Aは論拠不足を修正し切れなかった。"
    assert takeaway["quote"].startswith("「")


def test_normalize_summary_keeps_or_builds_gemini_quote():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bが押した。",
            "confidence": "Medium",
            "turning_point": "Turn 4でBが押し返した。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "そこが崩れる。", "reason": "ここで傾いた。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "定義の後退", "quote_excerpt": "定義を広げた。", "why_one_sentence": "定義を守れなかった。", "how_to_fix": "最初の基準を守るべきだった。"},
            "gemini_quote": {"text": "定義を崩した側が、勝負を取る。"},
            "key_disagreement_top3": ["x"],
        }
    )

    quote = summary["gemini_quote"]["text"]
    assert quote
    assert quote.startswith("「")
    assert len(quote.strip("「」")) <= 25


def test_normalize_summary_replaces_generic_gemini_quote_with_match_specific_line():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bが押した。",
            "confidence": "Medium",
            "turning_point": "Turn 4で物理法則が可能性論を止めた。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "可能性では物理法則は動かない。", "reason": "ここで傾いた。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "抽象逃避", "quote_excerpt": "可能性なら残る。", "why_one_sentence": "可能性を広げたが物理法則に返せなかった。", "how_to_fix": "可能性ではなく観測可能な条件を出すべきだった。"},
            "gemini_quote": {"text": "基準を握った側が議論を支配する。"},
            "key_disagreement_top3": ["x"],
        }
    )

    quote = summary["gemini_quote"]["text"]
    assert "基準を握った側が議論を支配する" not in quote
    assert "物理法則" in quote or "可能性" in quote


def test_normalize_summary_builds_distinct_gemini_quotes_per_topic():
    ai_summary = _normalize_summary(
        {
            "winner": {"side": "B"},
            "reason_one_liner": "Bが押した。",
            "confidence": "Medium",
            "turning_point": "Turn 4で主観的経験が機能模倣を止めた。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "主観的経験がなければ感情ではない。", "reason": "ここで傾いた。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "未応答", "quote_excerpt": "振る舞いが似ていれば十分だ。", "why_one_sentence": "主観的経験に答えなかった。", "how_to_fix": "主観条件そのものを崩すべきだった。"},
            "key_disagreement_top3": ["x"],
        }
    )["gemini_quote"]["text"]
    crypto_summary = _normalize_summary(
        {
            "winner": {"side": "B"},
            "reason_one_liner": "Bが押した。",
            "confidence": "Medium",
            "turning_point": "Turn 4で将来分散が今の集中を消せないと示された。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "将来分散しても、今の集中は消えない。", "reason": "ここで傾いた。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "条件追加の後手化", "quote_excerpt": "今後分散すればいい。", "why_one_sentence": "将来条件を後から足した。", "how_to_fix": "現時点の分散指標を先に出すべきだった。"},
            "key_disagreement_top3": ["x"],
        }
    )["gemini_quote"]["text"]

    assert ai_summary != crypto_summary
    assert ("主観" in ai_summary or "感情" in ai_summary)
    assert ("将来" in crypto_summary or "集中" in crypto_summary or "分散" in crypto_summary)
    assert "…" not in ai_summary
    assert "…" not in crypto_summary
    assert ai_summary.endswith("。」")
    assert crypto_summary.endswith("。」")
    assert any(word in ai_summary for word in ["止まっ", "動かな", "崩れ", "守れな"])
    assert any(word in crypto_summary for word in ["止まっ", "動かな", "崩れ", "逃げ", "薄まっ"])


def test_normalize_summary_builds_conflict_quotes_for_four_topics():
    university = _normalize_summary(
        {
            "winner": {"side": "B"},
            "reason_one_liner": "Bが押した。",
            "confidence": "Medium",
            "turning_point": "Turn 4で学歴の看板が実力証明を支え切れなくなった。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "学歴があっても、実力の空白は埋まらない。", "reason": "ここで傾いた。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "論拠不足", "quote_excerpt": "大学さえ出ればいい。", "why_one_sentence": "大学の価値を実力証明に結びつけ切れなかった。", "how_to_fix": "大学の看板ではなく、具体的な訓練差を出すべきだった。"},
            "key_disagreement_top3": ["x"],
        }
    )["gemini_quote"]["text"]
    literature = _normalize_summary(
        {
            "winner": {"side": "A"},
            "reason_one_liner": "Aが押した。",
            "confidence": "Medium",
            "turning_point": "Turn 4で感動の読みが作者性の証明を支え切れなくなった。",
            "fatal_phrase": {"speaker": "A", "turn": 4, "text": "感動はあっても、作者性の証拠にはならない。", "reason": "ここで傾いた。"},
            "weak_spot": {"side": "B", "turn": 4, "speaker": "B", "label": "抽象逃避", "quote_excerpt": "読後感があれば作者性は十分だ。", "why_one_sentence": "感動を作者性の証拠へ飛躍させた。", "how_to_fix": "感動ではなく作者性を示す痕跡を出すべきだった。"},
            "key_disagreement_top3": ["x"],
        }
    )["gemini_quote"]["text"]

    assert "学歴" in university or "大学" in university or "実力" in university
    assert "感動" in literature or "作者性" in literature or "証拠" in literature
    assert university != literature
    assert "…" not in university
    assert "…" not in literature
    assert university.endswith("。」")
    assert literature.endswith("。」")
    assert any(word in university for word in ["動かなかった", "立たなかった", "崩れた", "薄まった"])
    assert any(word in literature for word in ["動かなかった", "立たなかった", "崩れた", "残った"])


def test_normalize_summary_gemini_quote_completes_sentence_without_ellipsis():
    summary = _normalize_summary(
        {
            "winner": {"side": "B"},
            "reason_one_liner": "Bが押した。",
            "confidence": "Medium",
            "turning_point": "Turn 4で主観的経験が機能模倣を止めた。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "主観的経験がなければ感情ではない。", "reason": "ここで傾いた。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "未応答", "quote_excerpt": "振る舞いが似ていれば十分だ。", "why_one_sentence": "主観的経験に答えなかった。", "how_to_fix": "主観条件そのものを崩すべきだった。"},
            "gemini_quote": {"text": "主観的経験に答えないまま、勝ち筋が止まった"},
            "key_disagreement_top3": ["x"],
        }
    )["gemini_quote"]["text"]

    assert "…" not in summary
    assert summary.endswith("。」")
    assert "止まった" in summary


def test_normalize_summary_keeps_winner_story_consistent_when_turning_point_favors_other_side():
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが押し切った。"},
            "reason_one_liner": "Aが最後に押し返した。",
            "confidence": "Medium",
            "momentum": {"a": 60, "b": 40},
            "turning_point": "Turn 4でBが前提を揺らした。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "その前提はもう壊れている。", "reason": "ここで揺れた。"},
            "weak_spot": {
                "side": "A",
                "turn": 4,
                "speaker": "A",
                "label": "論拠不足",
                "quote_excerpt": "健康寿命まで見ないと片手落ちだ。",
                "why_one_sentence": "Bが健康寿命の論点で押した。",
                "how_to_fix": "健康寿命の論点をもっと広げるべきだった。",
            },
            "gemini_takeaway": {
                "structural_explanation": "Bが議論の焦点を変えた。",
                "debate_dynamic": "Turn4でBが押し込んだ。",
                "quote": "Bが流れを握った。",
            },
            "gemini_quote": {"text": "Bが流れを握った。"},
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "A"
    assert summary["weak_spot"]["side"] == "B"
    assert summary["weak_spot"]["speaker"] == "B"
    assert "A" in summary["gemini_takeaway"]["debate_dynamic"]
    assert "Bが流れを握った" not in summary["gemini_quote"]["text"]
    assert "A" == summary["fatal_phrase"]["speaker"]


def test_normalize_summary_rejects_meta_strategy_fatal_phrase():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押し切った。"},
            "reason_one_liner": "Bが押し切った。",
            "confidence": "Medium",
            "turning_point": "Turn 4でBが押し返した。",
            "fatal_phrase": {
                "speaker": "B",
                "turn": 4,
                "text": "次の一手として検証指標を入れる。",
                "reason": "このラリーはここで締めに入れる。",
            },
            "weak_spot": {
                "side": "A",
                "turn": 4,
                "speaker": "A",
                "label": "論拠不足",
                "quote_excerpt": "証拠がない。",
                "why_one_sentence": "根拠が足りない。",
                "how_to_fix": "指標を足すべきだった。",
            },
            "key_disagreement_top3": ["x"],
        }
    )

    fatal = summary["fatal_phrase"]
    assert "次の一手" not in fatal["text"]
    assert "このラリー" not in fatal["reason"]
    assert fatal["speaker"] == "B"


def test_mock_turn_texts_do_not_reintroduce_old_meta_phrasing():
    result = run_debate(
        {
            "topic": "未来における野球の神様は大谷翔平か",
            "side_a": "はい。競技横断の影響力と二刀流の前例破壊が大きい。",
            "side_b": "まだ決めきれない。歴史評価と継続年数が足りない。",
            "turn_count": 5,
            "api_keys": {},
        }
    )

    forbidden_fragments = [
        "主戦場",
        "ここで締めに入れる",
        "このラリーは",
        "相手の最新発言",
        "受け身じゃない",
        "受けに回らない",
        "一つに絞って刺す",
        "新しい守備範囲を強制する",
        "この瞬間に",
        "もって押し切ろうとしている",
        "次の一手",
        "盤面",
        "戦略",
        "分析",
        "検証指標を入れる",
        "元の立場を使う",
    ]

    speeches = []
    for turn in result["debate"]["turns"]:
        speeches.extend([turn["a"], turn["b"]])

    for speech in speeches:
        assert not any(fragment in speech for fragment in forbidden_fragments)


def test_history_store_save_list_and_get_round_trip(tmp_path):
    db_path = tmp_path / "history.sqlite"
    record = {
        "id": "match_1",
        "fingerprint": "fp_1",
        "created_at": "2026-03-14T10:00:00+00:00",
        "topic": "AIは感情を持つか",
        "mode": "casual",
        "turn_count": 5,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "anthropic",
        "judge_provider": "gemini",
        "fighter_a_model": "GPT-5-mini",
        "fighter_b_model": "Claude Sonnet 4.5",
        "judge_model": "Gemini 2.5 Flash",
        "transcript_json": [{"turn": 1, "a": "持ちうる。", "b": "持たない。"}],
        "judge_json": {"winner": {"side": "B"}, "verdict_headline": "AIは感情を持つとは言い切れない"},
        "output_meta": "5 turns · A live · B live · J live",
    }

    saved = save_history_record(record, db_path)
    listed = list_history_records(db_path)
    loaded = get_history_record(saved["saved_id"], db_path)

    assert saved["saved_id"] == "match_1"
    assert saved["deduped"] is False
    assert len(listed) == 1
    assert listed[0]["topic"] == record["topic"]
    assert loaded["judge_json"]["winner"]["side"] == "B"
    assert loaded["transcript_json"][0]["a"] == "持ちうる。"


def test_history_store_upserts_on_fingerprint(tmp_path):
    db_path = tmp_path / "history.sqlite"
    first = {
        "id": "match_1",
        "fingerprint": "same_fp",
        "created_at": "2026-03-14T10:00:00+00:00",
        "topic": "仮想通貨は本当に分散しているか",
        "mode": "casual",
        "turn_count": 5,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "judge_provider": "gemini",
        "fighter_a_model": "GPT-5-mini",
        "fighter_b_model": "GPT-5-mini",
        "judge_model": "Gemini 2.5 Flash",
        "transcript_json": [],
        "judge_json": {"winner": {"side": "B"}, "verdict_headline": "今回はB優勢"},
        "output_meta": "5 turns · A live · B live · J live",
    }
    second = {
        **first,
        "id": "match_2",
        "created_at": "2026-03-14T11:00:00+00:00",
        "judge_json": {"winner": {"side": "A"}, "verdict_headline": "今回はA優勢"},
    }

    save_history_record(first, db_path)
    saved = save_history_record(second, db_path)
    listed = list_history_records(db_path)

    assert saved["deduped"] is True
    assert saved["saved_id"] == "match_1"
    assert len(listed) == 1
    assert listed[0]["judge_json"]["winner"]["side"] == "A"


def test_history_store_lists_newest_first(tmp_path):
    db_path = tmp_path / "history.sqlite"
    older = {
        "id": "match_old",
        "fingerprint": "fp_old",
        "created_at": "2026-03-14T09:00:00+00:00",
        "topic": "古い試合",
        "mode": "casual",
        "turn_count": 5,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "anthropic",
        "judge_provider": "gemini",
        "fighter_a_model": "GPT-5-mini",
        "fighter_b_model": "Claude Sonnet 4.5",
        "judge_model": "Gemini 2.5 Flash",
        "transcript_json": [],
        "judge_json": {"winner": {"side": "A"}},
        "output_meta": "",
    }
    newer = {
        **older,
        "id": "match_new",
        "fingerprint": "fp_new",
        "created_at": "2026-03-14T12:00:00+00:00",
        "topic": "新しい試合",
    }

    save_history_record(older, db_path)
    save_history_record(newer, db_path)

    listed = list_history_records(db_path)
    assert [item["id"] for item in listed] == ["match_new", "match_old"]


def test_history_store_lists_popular_by_likes_then_views_then_created_at(tmp_path):
    db_path = tmp_path / "history.sqlite"
    base = {
        "mode": "casual",
        "turn_count": 5,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "anthropic",
        "judge_provider": "gemini",
        "fighter_a_model": "GPT-5-mini",
        "fighter_b_model": "Claude Sonnet 4.5",
        "judge_model": "Gemini 2.5 Flash",
        "transcript_json": [],
        "judge_json": {"winner": {"side": "A"}},
        "output_meta": "",
    }
    save_history_record({**base, "id": "low", "fingerprint": "fp_low", "created_at": "2026-03-14T09:00:00+00:00", "topic": "low", "likes": 1, "views": 10}, db_path)
    save_history_record({**base, "id": "high", "fingerprint": "fp_high", "created_at": "2026-03-14T08:00:00+00:00", "topic": "high", "likes": 3, "views": 1}, db_path)
    save_history_record({**base, "id": "mid", "fingerprint": "fp_mid", "created_at": "2026-03-14T10:00:00+00:00", "topic": "mid", "likes": 3, "views": 5}, db_path)

    listed = list_history_records(db_path, sort="likes")
    assert [item["id"] for item in listed] == ["mid", "high", "low"]


def test_history_store_increments_views_and_likes(tmp_path):
    db_path = tmp_path / "history.sqlite"
    record = {
        "id": "match_1",
        "fingerprint": "fp_1",
        "created_at": "2026-03-14T10:00:00+00:00",
        "topic": "AIは感情を持つか",
        "mode": "casual",
        "turn_count": 5,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "anthropic",
        "judge_provider": "gemini",
        "fighter_a_model": "GPT-5-mini",
        "fighter_b_model": "Claude Sonnet 4.5",
        "judge_model": "Gemini 2.5 Flash",
        "transcript_json": [],
        "judge_json": {"winner": {"side": "B"}},
        "output_meta": "",
    }

    save_history_record(record, db_path)
    viewed = increment_history_metric("match_1", "views", db_path)
    liked = increment_history_metric("match_1", "likes", db_path)

    assert viewed["views"] == 1
    assert viewed["likes"] == 0
    assert liked["views"] == 1
    assert liked["likes"] == 1
