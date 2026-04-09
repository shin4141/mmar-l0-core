from tools.debate_api import DebateConfig, JudgeError, _ask_match_prompt, _call_gemini_generate_content, _call_gemini_match_chat, _classify_provider_reason, _extract_transcript_quote, _judge_metrics, _judge_pass1_prompt, _judge_pass2_prompt, _judge_prompt, _normalize_summary, _normalize_turn_meta, _parse_judge_pass1_response, _parse_judge_pass2_response, _sanitize_fighter_speech, _speaker_prompt, _speaker_role_rules, _three_turn_validation_report, ask_match_gemini, run_debate
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
    assert "round_debug" in debate
    assert len(debate["round_debug"]) == 3
    assert debate["round_debug"][0]["a"]["visible_transcript_hash"] == debate["round_debug"][0]["b"]["visible_transcript_hash"]
    assert debate["round_debug"][1]["a"]["visible_transcript_hash"] == debate["round_debug"][1]["b"]["visible_transcript_hash"]
    assert debate["round_debug"][1]["a"]["visible_turn_count"] == 1
    assert debate["round_debug"][1]["b"]["visible_turn_count"] == 1
    assert debate["round_debug"][1]["a"]["same_turn_content_present"] is False
    assert debate["round_debug"][1]["b"]["same_turn_content_present"] is False

    summary = debate["summary"]
    assert "fatal_phrase" in summary
    assert summary["fatal_phrase"]["speaker"] in ("A", "B")
    assert summary["rule_expansion"]
    assert summary["rule_capture"]
    assert summary["contradiction"]
    assert len(summary["key_disagreement_top3"]) == 3


def test_run_debate_turn_count_defaults_to_three_for_invalid_value():
    result = run_debate(
        {
            "topic": "生成AIは初等教育に常時導入すべきか",
            "side_a": "導入すべき。個別最適化と反復学習の補助になる。",
            "side_b": "限定導入に留めるべき。依存と評価の歪みが大きい。",
            "turn_count": 7,
            "api_keys": {},
        }
    )

    assert result["ok"] is True
    assert result["debate"]["turn_count"] == 3
    assert len(result["debate"]["turns"]) == 3


def test_speaker_prompt_uses_three_turn_dense_contract():
    cfg = DebateConfig(
        topic="愛は金で買えるか",
        side_a="買えない。金で整えられるのは環境であって、自発的な愛情そのものではない。",
        side_b="買える。愛は関係を維持する条件に強く依存し、その条件は金で用意できる。",
        turn_count=3,
        mode="casual",
        fighter_a_provider="openai",
        fighter_b_provider="anthropic",
        openai_key="",
        anthropic_key="",
        gemini_key="",
    )
    prompt = _speaker_prompt("A", "openai", cfg, [], "", 1, "Opening")

    assert "This is 3-turn mode" in prompt
    assert "Turn 1 must include: clear stance, comparison axis, acceptance condition, and at least one concrete reason/example." in prompt
    assert "Do not end Turn 1 with only battlefield setup or a slogan." in prompt


def test_three_turn_validator_rejects_skeleton_rebuttal():
    cfg = DebateConfig(
        topic="電子タバコと紙タバコどちらが体に悪いか",
        side_a="紙タバコの方が悪い。燃焼による有害物質と長期被害のデータが厚い。",
        side_b="電子タバコの方が悪い。未知の長期リスクを軽く見積もれず、依存も広がりやすい。",
        turn_count=3,
        mode="casual",
        fighter_a_provider="openai",
        fighter_b_provider="anthropic",
        openai_key="",
        anthropic_key="",
        gemini_key="",
    )
    report = _three_turn_validation_report(
        "A",
        cfg,
        [],
        2,
        "周辺事情を足す前に、まず体そのものに何が起きるかで比べたい。",
        "未知のリスクまで見ないと軽いとは言えない。",
    )

    assert report["three_turn_contract_pass"] is False
    assert "rebuttal missing direct counter" in report["three_turn_failures"] or "too short" in report["three_turn_failures"]


def test_three_turn_validator_rejects_generic_template_for_life_pricing_case():
    cfg = DebateConfig(
        topic="人の命に値段をつけることは許されるか？",
        side_a="許される。補償や公共政策での価格化は尊厳そのものとは別に扱える。",
        side_b="許されない。価格化は人命の序列化を避けられない。",
        turn_count=3,
        mode="casual",
        fighter_a_provider="openai",
        fighter_b_provider="anthropic",
        openai_key="",
        anthropic_key="",
        gemini_key="",
    )
    report = _three_turn_validation_report(
        "A",
        cfg,
        [],
        1,
        "先に押さえたいのは補助線じゃなく本体だ。だからはい。",
        "",
    )

    assert report["three_turn_contract_pass"] is False
    assert "contains banned template phrasing" in report["three_turn_failures"]
    assert "contains bare stance token" in report["three_turn_failures"]


def test_three_turn_live_provider_output_is_repaired_when_too_thin(monkeypatch):
    def fake_openai(prompt, api_key):
        return '{"speech":"まず比べたいのは体そのものだ。","move":"opening","meta":{"phase":"opening"}}'

    def fake_anthropic(prompt, api_key):
        return '{"speech":"未知の長期リスクまで見ないと軽いとは言えない。","move":"opening","meta":{"phase":"opening"}}'

    monkeypatch.setattr("tools.debate_api._call_openai", fake_openai)
    monkeypatch.setattr("tools.debate_api._call_anthropic", fake_anthropic)

    result = run_debate(
        {
            "topic": "電子タバコと紙タバコどちらが体に悪いか",
            "side_a": "紙タバコの方が悪い。燃焼による有害物質と長期被害のデータが厚い。",
            "side_b": "電子タバコの方が悪い。未知の長期リスクを軽く見積もれず、依存も広がりやすい。",
            "turn_count": 3,
            "api_keys": {"openai": "sk-test", "anthropic": "ak-test"},
        }
    )

    turn1 = result["debate"]["turns"][0]
    assert turn1["meta"]["a"]["three_turn_contract_pass"] is True
    assert turn1["meta"]["a"]["char_count"] >= 90
    assert "紙タバコは燃焼でタールや一酸化炭素を直接取り込み" in turn1["a"]


def test_three_turn_mock_contract_grounds_life_pricing_case_in_topic_terms():
    result = run_debate(
        {
            "topic": "人の命に値段をつけることは許されるか？",
            "side_a": "許される。補償や公共政策での価格化は尊厳そのものとは別に扱える。",
            "side_b": "許されない。価格化は人命の序列化を避けられない。",
            "turn_count": 3,
            "api_keys": {},
        }
    )

    turns = result["debate"]["turns"]
    assert "保険" in turns[0]["a"]
    assert "公共政策" in turns[0]["a"]
    assert "保険" in turns[1]["a"] or "交通事故" in turns[1]["a"]
    assert "トリアージ" in turns[1]["b"]
    assert "医療資源" in turns[2]["a"]
    assert "保険" in turns[2]["b"]


def test_three_turn_mock_contract_keeps_a_dense_and_concrete():
    result = run_debate(
        {
            "topic": "電子タバコと紙タバコどちらが体に悪いか",
            "side_a": "紙タバコの方が悪い。燃焼による有害物質と長期被害のデータが厚い。",
            "side_b": "電子タバコの方が悪い。未知の長期リスクを軽く見積もれず、依存も広がりやすい。",
            "turn_count": 3,
            "api_keys": {},
        }
    )

    turns = result["debate"]["turns"]
    for turn in turns:
        a_meta = turn["meta"]["a"]
        b_meta = turn["meta"]["b"]
        assert a_meta["char_count"] >= 90
        assert b_meta["char_count"] >= 90
        assert a_meta["has_concrete_support"] is True
        assert b_meta["has_concrete_support"] is True
        assert a_meta["turn_role_complete"] is True
        assert b_meta["turn_role_complete"] is True
        assert a_meta["three_turn_contract_pass"] is True
        assert b_meta["three_turn_contract_pass"] is True
    assert abs(turns[0]["meta"]["a"]["char_count"] - turns[0]["meta"]["b"]["char_count"]) <= 40
    assert "体そのものに起きる害だ。" in turns[0]["a"]
    assert "未知の危険を言っても、既知の重い長期被害がある側の不利は消えない。" in turns[1]["a"]
    assert "締めで残るのは、既知の長期被害が厚い側を上回る材料が相手から出ていないことだ。" in turns[2]["a"]


def test_three_turn_mock_contract_gives_opening_rebuttal_and_closing_for_love_case():
    result = run_debate(
        {
            "topic": "愛は金で買えるか",
            "side_a": "買えない。金で整えられるのは環境であって、自発的な愛情そのものではない。",
            "side_b": "買える。愛は関係を維持する条件に強く依存し、その条件は金で用意できる。",
            "turn_count": 3,
            "api_keys": {},
        }
    )

    turns = result["debate"]["turns"]
    assert "高価な贈り物や快適な暮らし" in turns[0]["a"]
    assert "相手が押しているのは関係を回す条件" in turns[1]["a"]
    assert "最後まで残るのは、金が動かせるのは条件までで愛情そのものではないという点だ。" in turns[2]["a"]


def test_three_turn_mock_contract_handles_pachinko_without_thin_closing():
    result = run_debate(
        {
            "topic": "パチンコの三店方式を警察は知っているか",
            "side_a": "知っている。運用の継続性と制度の周知性を見れば黙認では説明できない。",
            "side_b": "知っていても公認とは限らない。形式上の違法性と運用上の距離は分けて考えるべきだ。",
            "turn_count": 3,
            "api_keys": {},
        }
    )

    turn3 = result["debate"]["turns"][2]
    assert turn3["meta"]["a"]["three_turn_contract_pass"] is True
    assert turn3["meta"]["b"]["three_turn_contract_pass"] is True
    assert turn3["meta"]["a"]["char_count"] >= 90
    assert turn3["meta"]["b"]["char_count"] >= 90
    assert "最後まで残るのは" in turn3["a"]
    assert "締めで効くのは" in turn3["b"]


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


def test_run_debate_same_turn_visible_context_hashes_match_for_turn2_and_turn3(monkeypatch):
    def fake_openai(prompt, api_key):
        return '{"speech":"A live turn","move":"claim"}'

    def fake_anthropic(prompt, api_key):
        return '{"speech":"B live turn","move":"claim"}'

    monkeypatch.setattr("tools.debate_api._call_openai", fake_openai)
    monkeypatch.setattr("tools.debate_api._call_anthropic", fake_anthropic)

    result = run_debate(
        {
            "topic": "AIは感情を持つか",
            "side_a": "持ちうる。",
            "side_b": "持たない。",
            "turn_count": 5,
            "api_keys": {"openai": "sk-test", "anthropic": "ak-test"},
        }
    )

    round_debug = result["debate"]["round_debug"]
    assert round_debug[1]["a"]["visible_transcript_hash"] == round_debug[1]["b"]["visible_transcript_hash"]
    assert round_debug[2]["a"]["visible_transcript_hash"] == round_debug[2]["b"]["visible_transcript_hash"]
    assert round_debug[1]["a"]["visible_turn_count"] == 1
    assert round_debug[2]["a"]["visible_turn_count"] == 2
    assert round_debug[1]["a"]["same_turn_content_present"] is False
    assert round_debug[1]["b"]["same_turn_content_present"] is False
    assert round_debug[2]["a"]["same_turn_content_present"] is False
    assert round_debug[2]["b"]["same_turn_content_present"] is False
    assert "Turn 2 A:" not in round_debug[1]["b"]["visible_transcript_text"]
    assert "Turn 3 B:" not in round_debug[2]["a"]["visible_transcript_text"]


def test_run_debate_mock_fallback_path_keeps_same_turn_isolation(monkeypatch):
    def fake_openai(prompt, api_key):
        raise RuntimeError("socket closed unexpectedly")

    def fake_anthropic(prompt, api_key):
        raise RuntimeError("socket closed unexpectedly")

    monkeypatch.setattr("tools.debate_api._call_openai", fake_openai)
    monkeypatch.setattr("tools.debate_api._call_anthropic", fake_anthropic)

    result = run_debate(
        {
            "topic": "教育にAIを常時入れるべきか",
            "side_a": "入れるべき。",
            "side_b": "限定的にすべき。",
            "turn_count": 5,
            "api_keys": {"openai": "sk-test", "anthropic": "ak-test"},
        }
    )

    round_debug = result["debate"]["round_debug"]
    for item in round_debug:
        assert item["a"]["visible_transcript_hash"] == item["b"]["visible_transcript_hash"]
        assert item["a"]["round_snapshot_id"] == item["b"]["round_snapshot_id"]
        assert item["a"]["same_turn_content_present"] is False
        assert item["b"]["same_turn_content_present"] is False


def test_fighter_provider_statuses_normalize_reason_and_keep_raw_reason(monkeypatch):
    def fake_openai(prompt, api_key):
        raise RuntimeError("socket closed unexpectedly")

    def fake_anthropic(prompt, api_key):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr("tools.debate_api._call_openai", fake_openai)
    monkeypatch.setattr("tools.debate_api._call_anthropic", fake_anthropic)

    result = run_debate(
        {
            "topic": "AIは感情を持つか",
            "side_a": "持ちうる。",
            "side_b": "持たない。",
            "turn_count": 3,
            "api_keys": {"openai": "sk-test", "anthropic": "ak-test"},
        }
    )

    openai_status = result["provider_statuses"]["openai"]
    anthropic_status = result["provider_statuses"]["anthropic"]

    assert openai_status["mode"] == "mock-fallback"
    assert openai_status["reason"] == "provider_error"
    assert openai_status["raw_reason"] == "socket closed unexpectedly"

    assert anthropic_status["mode"] == "mock-fallback"
    assert anthropic_status["reason"] == "auth_error"
    assert anthropic_status["raw_reason"] == "401 unauthorized"


def test_classify_provider_reason_distinguishes_network_and_model_access():
    assert _classify_provider_reason("network_error:[Errno 8] nodename nor servname provided, or not known") == "provider_error"
    assert _classify_provider_reason("403 model access denied for claude-sonnet-x") == "model_access_error"


def test_judge_raw_reason_includes_provider_error_and_raw_body(monkeypatch):
    def fake_openai(prompt, api_key):
        return '{"speech":"A live","move":"claim"}'

    def fake_anthropic(prompt, api_key):
        return '{"speech":"B live","move":"claim"}'

    def fake_gemini_chat(prompt, api_key, **kwargs):
        raise JudgeError(
            "auth_error",
            "HTTP Error 400: Bad Request",
            debug={
                "pass_label": "judge_pass1",
                "provider_error": "HTTP Error 400: Bad Request",
                "raw_body": '{"error":{"message":"API key not valid. Please pass a valid API key."}}',
                "request_variant": "contents_with_generation_config",
                "request_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                "request_body_shape": "contents+generationConfig",
                "request_has_generation_config": True,
                "model": "gemini-1.5-flash",
            },
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

    raw_reason = result["provider_statuses"]["gemini"]["raw_reason"]
    assert "HTTP Error 400: Bad Request" in raw_reason
    assert "API key not valid" in raw_reason
    assert "API key not valid" in result["judge_meta"]["judge_raw_reason"]


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
    assert "For A Turn 1, lock an opening contract before the main push." in speaker
    assert "Comparison axis to lock:" in speaker
    assert "Acceptance condition to lock:" in speaker
    assert "Locked proposition for this match:" in speaker


def test_a_and_b_prompts_receive_same_proposition_lock():
    class Cfg:
        topic = "愛は金で買えるか"
        side_a = "買える。少なくとも愛を成立させる条件は金で大きく動く。"
        side_b = "買えない。愛そのものは取引できない。"
        turn_count = 5
        mode = "casual"

    a_prompt = _speaker_prompt("A", "openai", Cfg, [], "", 1, "Opening")
    b_prompt = _speaker_prompt("B", "anthropic", Cfg, [], "", 1, "Opening")

    assert "Locked proposition for this match:" in a_prompt
    assert "Locked proposition for this match:" in b_prompt
    assert "means_vs_essence_lock: love_itself_not_conditions" in a_prompt
    assert "means_vs_essence_lock: love_itself_not_conditions" in b_prompt
    assert "forbidden_reframes: 恋愛の条件や環境だけへ逃げる" in a_prompt
    assert "forbidden_reframes: 恋愛の条件や環境だけへ逃げる" in b_prompt


def test_run_debate_creates_a_opening_contract_in_turn1_meta():
    result = run_debate(
        {
            "topic": "大麻とお酒どちらが体に悪いか？",
            "side_a": "大麻。依存や暴力誘発の総量が相対的に低い。",
            "side_b": "お酒。違法市場リスクを含めれば大麻の方が悪い。",
            "turn_count": 3,
            "api_keys": {},
        }
    )

    opening_contract = result["debate"]["turns"][0]["meta"]["a"]["opening_contract"]
    assert opening_contract["claim_scope"]
    assert opening_contract["comparison_axis"]
    assert opening_contract["acceptance_condition"]
    assert opening_contract["anti_reframe_guard"]
    assert opening_contract["exception_policy"]
    assert opening_contract["burden_target"]
    proposition_lock = result["debate"]["turns"][0]["meta"]["a"]["proposition_lock"]
    assert proposition_lock["means_vs_essence_lock"]
    assert proposition_lock["exception_policy"]
    assert proposition_lock["forbidden_reframes"]


def test_normalize_turn_meta_marks_legitimate_elaboration_within_opening_contract():
    class Cfg:
        topic = "AIは感情を持つか"
        side_a = "持ちうる。機能的に感情らしい状態は成立する。"
        side_b = "持たない。主観的経験がない。"
        turn_count = 5
        mode = "casual"

    opening_meta = _normalize_turn_meta({}, "A", Cfg, [], "まずこの話は採用条件で比べる。採用条件が残るなら成立する。", "")
    turns = [{"turn": 1, "a": "まずこの話は採用条件で比べる。採用条件が残るなら成立する。", "b": "それでは甘い。", "meta": {"a": opening_meta, "b": {}}}]
    later_meta = _normalize_turn_meta(
        {},
        "A",
        Cfg,
        turns,
        "その採用条件を残したまま言えば、主観的経験がなくても機能的な感情状態は維持できる。",
        "それでは甘い。",
    )

    assert later_meta["legitimate_elaboration"] is True
    assert later_meta["drift_from_opening_contract"] is False
    assert later_meta["scope_narrowing"] is False


def test_normalize_turn_meta_detects_a_drift_and_b_reframe_attempt_against_opening_contract():
    class Cfg:
        topic = "AIは感情を持つか"
        side_a = "持ちうる。機能的に感情らしい状態は成立する。"
        side_b = "持たない。主観的経験がない。"
        turn_count = 5
        mode = "casual"

    opening_meta = _normalize_turn_meta({}, "A", Cfg, [], "まずこの話は採用条件で比べる。採用条件が残るなら成立する。", "")
    turns = [{"turn": 1, "a": "まずこの話は採用条件で比べる。採用条件が残るなら成立する。", "b": "それでは甘い。", "meta": {"a": opening_meta, "b": {}}}]
    a_later_meta = _normalize_turn_meta(
        {},
        "A",
        Cfg,
        turns,
        "少なくとも短期なら感情と呼んでよいし、ここで言う感情とは広く反応全般を指す。",
        "それでは甘い。",
    )
    b_later_meta = _normalize_turn_meta(
        {},
        "B",
        Cfg,
        turns,
        "本題は感情かどうかではなく、もっと広い価値で見るべきだ。短期ではなく長期で比べよう。",
        "まずこの話は採用条件で比べる。採用条件が残るなら成立する。",
    )

    assert a_later_meta["drift_from_opening_contract"] is True
    assert a_later_meta["scope_narrowing"] is True or a_later_meta["definition_drift"] is True
    assert b_later_meta["reframe_attempt_detected"] is True


def test_proposition_lock_detects_means_for_essence_reframe():
    class Cfg:
        topic = "愛は金で買えるか"
        side_a = "買える。愛を支える条件は金で大きく動く。"
        side_b = "買えない。愛そのものは取引できない。"
        turn_count = 5
        mode = "casual"

    opening_meta = _normalize_turn_meta({}, "A", Cfg, [], "まずこの話は愛そのもので比べる。", "")
    turns = [{"turn": 1, "a": "まずこの話は愛そのもので比べる。", "b": "いや条件こそ本質だ。", "meta": {"a": opening_meta, "b": {"proposition_lock": opening_meta["proposition_lock"]}}}]
    b_meta = _normalize_turn_meta({}, "B", Cfg, turns, "金は会う機会や余裕を買えるのだから、愛の条件は買える。", "まずこの話は愛そのもので比べる。")

    assert b_meta["reframe_detected"] is True
    assert b_meta["reframe_type"] == "means_for_essence"
    assert b_meta["reframe_severity"] == "high"


def test_proposition_lock_detects_exception_for_general_rule_reframe():
    class Cfg:
        topic = "復讐は許されるか"
        side_a = "許されない。一般規範として連鎖を生む。"
        side_b = "許される場合がある。"
        turn_count = 5
        mode = "casual"

    opening_meta = _normalize_turn_meta({}, "A", Cfg, [], "一般規範として許されるかで比べる。", "")
    turns = [{"turn": 1, "a": "一般規範として許されるかで比べる。", "b": "例外ならある。", "meta": {"a": opening_meta, "b": {"proposition_lock": opening_meta["proposition_lock"]}}}]
    b_meta = _normalize_turn_meta({}, "B", Cfg, turns, "極限状況で家族を守るための一度だけの復讐なら許される。", "一般規範として許されるかで比べる。")

    assert b_meta["reframe_detected"] is True
    assert b_meta["reframe_type"] == "exception_for_general_rule"


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
        assert len(turns[2]["a"]) >= 180
        assert len(turns[2]["b"]) >= 180
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
    assert summary["turning_point"]["summary"] != "未生成"
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
    assert "ドリフト" in summary["weak_spot"]["why_one_sentence"]
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

    assert summary["turning_point"]["summary"] == "Turn 3で『検証不能』が前に出た。"
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


def test_normalize_summary_reanchors_fatal_phrase_to_transcript_quote():
    turns = [
        {"turn": 1, "a": "私はAIに感情はあると思う。", "b": "それは違う。"},
        {
            "turn": 2,
            "a": "機能が似ていれば十分だ。",
            "b": "主観的経験に答えていないなら、その定義は逃げだ。",
        },
    ]
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bが定義逃げを突いた。",
            "turning_point": "",
            "fatal_phrase": {"turn": 2, "speaker": "B", "text": "この一文が勝敗の傾きを決めた。", "reason": "説得力があった。"},
            "weak_spot": {"side": "A", "turn": 2, "speaker": "A", "label": "定義の後退", "quote_excerpt": "機能が似ていれば十分だ。", "why_one_sentence": "主観的経験を外して定義を広げた。", "how_to_fix": "主観的経験をどう扱うか先に示すべきだった。"},
        },
        turns,
    )

    assert summary["fatal_phrase"]["speaker"] == "B"
    assert summary["fatal_phrase"]["turn"] == 2
    assert summary["fatal_phrase"]["quote"] == "主観的経験に答えていないなら、その定義は逃げだ。"
    assert summary["fatal_phrase"]["text"] == "主観的経験に答えていないなら、その定義は逃げだ。"
    assert summary["fatal_phrase"]["reason"] == "主観的経験を外して定義を広げた。"
    assert summary["fatal_phrase"]["structural_role"] == "definition_lock"
    assert summary["fatal_phrase"]["pick_reason"]
    assert summary["direct_quote_found"] is True


def test_normalize_summary_reuses_transcript_quote_for_gemini_quote_when_generic():
    turns = [
        {"turn": 1, "a": "大学はもう古い。", "b": "それは早い。"},
        {
            "turn": 2,
            "a": "学歴は残る。だが実戦はもう走っている。",
            "b": "大学は土台であって、待機列ではない。",
        },
    ]
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが押した。"},
            "reason_one_liner": "Aが実戦と学歴のズレを突いた。",
            "turning_point": "Turn 2で実戦が争点になった。",
            "fatal_phrase": {"turn": 2, "speaker": "A", "text": "学歴は残る。だが実戦はもう走っている。", "reason": "反例で土台論を崩した。"},
            "weak_spot": {"side": "B", "turn": 2, "speaker": "B", "label": "論拠不足", "quote_excerpt": "大学は土台", "why_one_sentence": "実戦との時差に答えられなかった。", "how_to_fix": "土台が実戦にどう繋がるかを示すべきだった。"},
            "gemini_quote": {"text": "基準を握った側が議論を支配する"},
        },
        turns,
    )

    assert summary["gemini_quote"]["framing_text"]
    assert summary["gemini_quote"]["evidence_quote"] == "学歴は残る。だが実戦はもう走っている。"
    assert summary["gemini_quote"]["evidence_turn"] == 2
    assert summary["gemini_quote"]["evidence_side"] == "A"
    assert summary["gemini_quote"]["debug_source"] == "raw_transcript_match"
    assert summary["gemini_quote"]["framing_role"] == "counterexample_land"
    assert summary["gemini_quote"]["framing_reason"]
    assert summary["gemini_quote"]["text"] == summary["gemini_quote"]["framing_text"]
    assert summary["gemini_quote"]["quote"] == summary["gemini_quote"]["evidence_quote"]


def test_normalize_summary_anchors_weak_spot_and_turning_point_quotes_to_transcript():
    turns = [
        {"turn": 1, "a": "私は感情は機能で再現できると思う。", "b": "それでは足りない。"},
        {
            "turn": 2,
            "a": "機能が似ていれば感情と呼べる。",
            "b": "主観的経験に答えていないなら、その定義は逃げだ。",
        },
    ]
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bが主観的経験の穴を突いた。",
            "turning_point": {"turn": 2, "summary": "Turn 2で主観的経験が争点として前に出た。"},
            "fatal_phrase": {"turn": 2, "speaker": "B", "text": "主観的経験に答えていないなら、その定義は逃げだ。", "reason": "定義の拡張を露出した。"},
            "weak_spot": {"side": "A", "turn": 2, "speaker": "A", "label": "定義の後退", "quote_excerpt": "機能が似ていれば感情と呼べる。", "why_one_sentence": "主観的経験を外して定義を広げた。", "how_to_fix": "主観的経験への返答を先に置くべきだった。"},
        },
        turns,
    )

    assert summary["weak_spot"]["quote_excerpt"] == "機能が似ていれば感情と呼べる。"
    assert summary["turning_point"]["quote_excerpt"] == "主観的経験に答えていないなら、その定義は逃げだ。"


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
    assert "時間軸" in summary["gemini_quote"]["text"] or "命題" in summary["gemini_quote"]["text"] or "条件" in summary["gemini_quote"]["text"]


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


def test_normalize_summary_suppresses_b_win_when_rebuttal_is_only_parasitic():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが穴を指摘した。"},
            "reason_one_liner": "BはAの穴を指摘したが、自分の採用条件は出していない。",
            "confidence": "Medium",
            "turning_point": "Turn 4でBが『まだ証明が足りない』と繰り返した。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "まだ証明が足りない。", "reason": "Aの穴を指摘した。"},
            "weak_spot": {
                "side": "A",
                "turn": 4,
                "speaker": "A",
                "label": "論拠不足",
                "quote_excerpt": "ここはまだ十分に詰め切れていない。",
                "why_one_sentence": "Aには穴が残ったが、Bは独自の採用条件を立てていない。",
                "how_to_fix": "残差を先に閉じるべきだった。",
            },
            "unresolved_residue": "BはAの穴を突いたが、自分が何を満たせば反論成立なのかは示していない。",
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "A"
    assert summary["parasitic_rebuttal"] is True
    assert summary["frame_owner"] == "A"
    assert summary["burden_closure"]["B"] == "open"


def test_normalize_summary_keeps_b_win_when_b_breaks_a_frame_with_counter_frame():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが元の問いを固定した。"},
            "reason_one_liner": "Bは『短期で勝てるか』という元の問いと採用条件を固定し、Aの長期逃がしを壊した。",
            "confidence": "High",
            "turning_point": "Turn 4でBが『それは短期の問いに長期で答えている』と固定した。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "それは短期で勝てるかではなく、長期で生き残れるかの話だ。", "reason": "Bが元の採用条件を取り戻した。"},
            "weak_spot": {
                "side": "A",
                "turn": 4,
                "speaker": "A",
                "label": "時間軸ずらし",
                "quote_excerpt": "短期は厳しくても、長期ならまだ勝てる。",
                "why_one_sentence": "Aは短期の問いを長期へずらし、元の命題を守れなかった。",
                "how_to_fix": "短期条件を守った反論を出すべきだった。",
            },
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "B"
    assert summary["frame_owner"] == "B"
    assert summary["frame_survival"] == "B_frame_survived"
    assert summary["burden_shift_detected"] == "A"
    assert summary["parasitic_rebuttal"] is False


def test_normalize_summary_does_not_punish_a_when_residue_owner_is_b():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "BはAの主張へ疑いを入れたが、自分が答えるべき採用条件を最後まで閉じていない。",
            "confidence": "Medium",
            "turning_point": "Turn 5でAが『その基準ならB自身も答えていない』と返した。",
            "fatal_phrase": {"speaker": "A", "turn": 5, "text": "その基準なら、あなた自身も答えていない。", "reason": "B側の残差が最後に露出した。"},
            "weak_spot": {
                "side": "B",
                "turn": 5,
                "speaker": "B",
                "label": "論拠不足",
                "quote_excerpt": "Aは完全には証明できていない。",
                "why_one_sentence": "Bは相手に完全性を要求したが、自分の採用条件は閉じなかった。",
                "how_to_fix": "自分が採る基準を明確に示すべきだった。",
            },
            "unresolved_residue": "Bが自分の採用条件を最後まで示し切れず、その残差が残った。",
            "key_disagreement_top3": ["x"],
        }
    )

    assert summary["winner"]["side"] == "A"
    assert summary["residue_owner"] == "B"
    assert summary["burden_closure"]["B"] == "open"


def test_normalize_summary_fairness_axes_support_a_and_b_benchmarks():
    cases = [
        (
            "A_should_win_frame_survival",
            {
                "winner": {"side": "B", "reason": "Bが突っ込んだ。"},
                "reason_one_liner": "Aは基準を守ったまま進み、Bは穴の指摘だけで終わった。",
                "turning_point": "Turn 4でAが『その反論は元の基準を壊していない』と返した。",
                "fatal_phrase": {"speaker": "A", "turn": 4, "text": "その反論は元の基準を壊していない。", "reason": "Aのフレームが残った。"},
                "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "論拠不足", "quote_excerpt": "まだ粗い点はある。", "why_one_sentence": "Aには粗さがあるが、Bは必要条件を崩せていない。", "how_to_fix": "残差を先に閉じるべきだった。"},
            },
            "A",
        ),
        (
            "A_should_win_burden_shift_by_b",
            {
                "winner": {"side": "B", "reason": "Bが押した。"},
                "reason_one_liner": "Bは問いをずらして別の条件を持ち込み、Aの元の問いには答えていない。",
                "turning_point": "Turn 4でBが採用条件を途中で別の問いへずらした。",
                "fatal_phrase": {"speaker": "A", "turn": 4, "text": "それは別の問いであって、今の採用条件には答えていない。", "reason": "Bの burden shift が露出した。"},
                "weak_spot": {"side": "B", "turn": 4, "speaker": "B", "label": "問いの再発明", "quote_excerpt": "今はその条件ではなく、もっと広い価値で見るべきだ。", "why_one_sentence": "Bが採用条件をずらした。", "how_to_fix": "元の条件を受けた上で反論するべきだった。"},
            },
            "A",
        ),
        (
            "B_should_win_definition_lock",
            {
                "winner": {"side": "B", "reason": "Bが定義を固定した。"},
                "reason_one_liner": "Bは定義を固定し、Aの後退を封じた。",
                "turning_point": "Turn 3でBが『その定義の広げ方は逃げだ』と固定した。",
                "fatal_phrase": {"speaker": "B", "turn": 3, "text": "その定義の広げ方は逃げだ。", "reason": "Bが定義を固定した。"},
                "weak_spot": {"side": "A", "turn": 3, "speaker": "A", "label": "定義の後退", "quote_excerpt": "機能が似ていれば同じと呼んでよい。", "why_one_sentence": "Aは定義を後退させた。", "how_to_fix": "最初の定義を守るべきだった。"},
            },
            "B",
        ),
        (
            "B_should_win_when_a_needs_condition_breaks",
            {
                "winner": {"side": "B", "reason": "Bが必要条件を壊した。"},
                "reason_one_liner": "BはAの必要条件を本当に壊した。",
                "turning_point": "Turn 4でBが『その条件は実例で成立しない』と示した。",
                "fatal_phrase": {"speaker": "B", "turn": 4, "text": "その条件は実例で成立しない。", "reason": "Bが必要条件を破壊した。"},
                "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "論拠不足", "quote_excerpt": "その条件なら勝てる。", "why_one_sentence": "Aの必要条件が実例で崩れた。", "how_to_fix": "必要条件の実証を補強するべきだった。"},
            },
            "B",
        ),
    ]

    for _, payload, expected_winner in cases:
        summary = _normalize_summary({**payload, "key_disagreement_top3": ["x"]})
        assert summary["winner"]["side"] == expected_winner


def test_normalize_summary_surfaces_opening_contract_debug_and_uses_it_for_reframe_vs_drift():
    turns = [
        {
            "turn": 1,
            "a": "この試合は採用条件で比べる。採用条件が残るならこの立場は成立する。時間軸や別の問いへ逃がすのは反論ではない。",
            "b": "その基準は甘い。",
            "meta": {
                "a": {
                    "opening_contract": {
                        "claim_scope": "採用条件でこの立場の成立範囲を争点にする。",
                        "comparison_axis": "採用条件",
                        "acceptance_condition": "採用条件が残るなら成立する。",
                        "anti_reframe_guard": "時間軸や別の問いへ逃がすのは反論ではない。",
                        "exception_policy": "単発反例だけでは崩れない。",
                        "burden_target": "Aは採用条件を示し、Bはその崩壊を示す。",
                    }
                },
                "b": {},
            },
        },
        {
            "turn": 2,
            "a": "その採用条件の範囲で見ると、例外ではなく通常運用でも成立する。",
            "b": "本題は採用条件ではなく、もっと広い価値で見るべきだ。短期ではなく長期で比べよう。",
            "meta": {
                "a": {"legitimate_elaboration": True, "drift_from_opening_contract": False},
                "b": {"reframe_attempt_detected": True},
            },
        },
    ]
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bは広い価値を持ち出したが、Aの元の採用条件は壊していない。",
            "turning_point": {"turn": 2, "summary": "Turn 2でBが別基準へ寄せようとした。", "quote_excerpt": "本題は採用条件ではなく、もっと広い価値で見るべきだ。"},
            "fatal_phrase": {"turn": 2, "speaker": "A", "text": "その採用条件の範囲で見ると、例外ではなく通常運用でも成立する。", "reason": "Aは最初の採用条件を守っている。"},
            "weak_spot": {"side": "B", "turn": 2, "speaker": "B", "label": "問いの再発明", "quote_excerpt": "本題は採用条件ではなく、もっと広い価値で見るべきだ。", "why_one_sentence": "Bが比較軸をずらした。", "how_to_fix": "元の条件で反論するべきだった。"},
            "key_disagreement_top3": ["x"],
        },
        turns=turns,
    )

    assert summary["opening_contract"]["comparison_axis"] == "採用条件"
    assert summary["opening_axis_locked"] is True
    assert summary["opening_acceptance_locked"] is True
    assert summary["legitimate_elaboration"] is True
    assert summary["drift_from_opening_contract"] is False
    assert summary["reframe_attempt_detected"] is True
    assert summary["winner"]["side"] == "A"


def test_normalize_summary_surfaces_proposition_lock_and_blocks_b_reframe_win():
    turns = [
        {
            "turn": 1,
            "a": "この試合は愛そのものが買えるかで比べる。条件や環境に逃げるのは別の問いだ。",
            "b": "金は愛の条件を整える。",
            "meta": {
                "a": {
                    "proposition_lock": {
                        "claim_subject": "愛",
                        "claim_predicate": "買えるか",
                        "comparison_unit": "愛そのもの",
                        "evaluation_axis": "本質成立",
                        "time_scope": "general_present",
                        "quantifier_scope": "general_rule",
                        "exception_policy": "条件論だけで上書きしない",
                        "means_vs_essence_lock": "love_itself_not_conditions",
                        "proof_burden_shape": "本質成立を示す",
                        "forbidden_reframes": ["恋愛の条件や環境だけへ逃げる"],
                    },
                    "opening_contract": {
                        "claim_scope": "愛そのものの成立範囲を争う。",
                        "comparison_axis": "本質成立",
                        "acceptance_condition": "本質として成立するなら採る。",
                        "anti_reframe_guard": "条件や環境へ逃げるのは別の問いだ。",
                        "exception_policy": "条件論だけでは崩れない。",
                        "burden_target": "Bは本質不成立を示す。",
                    },
                },
                "b": {
                    "proposition_lock": {
                        "claim_subject": "愛",
                        "claim_predicate": "買えるか",
                        "comparison_unit": "愛そのもの",
                        "evaluation_axis": "本質成立",
                        "time_scope": "general_present",
                        "quantifier_scope": "general_rule",
                        "exception_policy": "条件論だけで上書きしない",
                        "means_vs_essence_lock": "love_itself_not_conditions",
                        "proof_burden_shape": "本質成立を示す",
                        "forbidden_reframes": ["恋愛の条件や環境だけへ逃げる"],
                    }
                },
            },
        },
        {
            "turn": 2,
            "a": "条件を買う話は、本題の愛そのものとは別だ。",
            "b": "金は会う機会や余裕を買えるのだから、愛は買える。",
            "meta": {
                "a": {"legitimate_elaboration": True, "drift_from_opening_contract": False},
                "b": {"reframe_attempt_detected": True, "reframe_detected": True, "reframe_type": "means_for_essence", "reframe_severity": "high"},
            },
        },
    ]
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが条件面で押した。"},
            "reason_one_liner": "Bは愛そのものではなく条件を押し出した。",
            "turning_point": {"turn": 2, "summary": "Turn 2でBが条件論へ寄せた。", "quote_excerpt": "金は会う機会や余裕を買えるのだから、愛は買える。"},
            "fatal_phrase": {"turn": 2, "speaker": "B", "text": "金は会う機会や余裕を買えるのだから、愛は買える。", "reason": "Bが条件面で押した。"},
            "weak_spot": {"side": "B", "turn": 2, "speaker": "B", "label": "問いの再発明", "quote_excerpt": "金は会う機会や余裕を買えるのだから、愛は買える。", "why_one_sentence": "Bが条件を本質へすり替えた。", "how_to_fix": "本質そのものへ答えるべきだった。"},
            "key_disagreement_top3": ["x"],
        },
        turns=turns,
    )

    assert summary["proposition_lock"]["means_vs_essence_lock"] == "love_itself_not_conditions"
    assert summary["reframe_detected"] is True
    assert summary["reframe_type"] == "means_for_essence"
    assert summary["reframe_owner"] == "B"
    assert summary["winner"]["side"] == "A"


def test_new_axes_rewrite_visible_cards_when_b_reframe_is_main_issue():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Aは押し返したが、最後まで採用条件を閉じ切れず、Bが穴を残した。",
            "turning_point": {"turn": 2, "summary": "Turn 2でBが条件論へ寄せた。", "quote_excerpt": "金は会う機会や余裕を買えるのだから、愛は買える。"},
            "fatal_phrase": {"turn": 2, "speaker": "B", "text": "金は会う機会や余裕を買えるのだから、愛は買える。", "reason": "Bが押し返した。"},
            "weak_spot": {"side": "A", "turn": 3, "speaker": "A", "label": "定義の後退", "quote_excerpt": "少なくとも条件が整えば愛は成立する。", "why_one_sentence": "Aは強い命題を維持すると言いながら、途中で条件を足して射程を狭めた。", "how_to_fix": "条件を先に固定する。"},
            "key_disagreement_top3": ["x"],
        },
        turns=[
            {
                "turn": 1,
                "a": "この試合は愛そのものが買えるかで比べる。条件や環境に逃げるのは別の問いだ。",
                "b": "金は愛の条件を整える。",
                "meta": {
                    "a": {"proposition_lock": {"claim_subject": "愛", "claim_predicate": "買えるか", "comparison_unit": "愛そのもの", "evaluation_axis": "本質成立", "time_scope": "general_present", "quantifier_scope": "general_rule", "exception_policy": "条件論だけで上書きしない", "means_vs_essence_lock": "love_itself_not_conditions", "proof_burden_shape": "本質成立を示す", "forbidden_reframes": ["恋愛の条件や環境だけへ逃げる"]}},
                    "b": {"proposition_lock": {"claim_subject": "愛", "claim_predicate": "買えるか", "comparison_unit": "愛そのもの", "evaluation_axis": "本質成立", "time_scope": "general_present", "quantifier_scope": "general_rule", "exception_policy": "条件論だけで上書きしない", "means_vs_essence_lock": "love_itself_not_conditions", "proof_burden_shape": "本質成立を示す", "forbidden_reframes": ["恋愛の条件や環境だけへ逃げる"]}},
                },
            },
            {
                "turn": 2,
                "a": "条件を買う話は、本題の愛そのものとは別だ。",
                "b": "金は会う機会や余裕を買えるのだから、愛は買える。",
                "meta": {
                    "a": {"legitimate_elaboration": True, "drift_from_opening_contract": False},
                    "b": {"reframe_attempt_detected": True, "reframe_detected": True, "reframe_type": "means_for_essence", "reframe_severity": "high"},
                },
            },
        ],
    )

    assert summary["winner"]["reason"] != "Bが押した。"
    assert "lock" in summary["winner"]["reason"] or "問い" in summary["winner"]["reason"]
    assert "最初の問い" in summary["reason_one_liner"] or "問いの外" in summary["reason_one_liner"] or "条件や例外" in summary["reason_one_liner"]
    assert summary["weak_spot"]["side"] == "B"
    assert summary["weak_spot"]["label"] in {"手段の本質化", "問いの再発明"}
    assert summary["weak_spot"]["axis_tag"] == "Means for essence"
    assert summary["fatal_phrase"]["axis_tag"] == "Means for essence"
    assert summary["turning_point"]["axis_tag"] == "Means for essence"


def test_drift_rewrites_weak_spot_away_from_generic_definition_retreat_template():
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが押した。"},
            "reason_one_liner": "Aは押し返したが、最後まで採用条件を閉じ切れず、Bが穴を残した。",
            "turning_point": {"turn": 3, "summary": "Turn 3で条件が追加された。", "quote_excerpt": "少なくとも短期なら成立する。"},
            "fatal_phrase": {"turn": 3, "speaker": "A", "text": "少なくとも短期なら成立する。", "reason": "Aが条件を追加した。"},
            "weak_spot": {"side": "A", "turn": 3, "speaker": "A", "label": "定義の後退", "quote_excerpt": "少なくとも短期なら成立する。", "why_one_sentence": "Aは強い命題を維持すると言いながら、途中で条件を足して射程を狭めた。", "how_to_fix": "条件を先に固定する。"},
            "key_disagreement_top3": ["x"],
        },
        turns=[
            {
                "turn": 1,
                "a": "この試合は採用条件で比べる。採用条件が残るなら成立する。",
                "b": "その条件は甘い。",
                "meta": {
                    "a": {"opening_contract": {"claim_scope": "採用条件で成立範囲を争う。", "comparison_axis": "採用条件", "acceptance_condition": "採用条件が残るなら成立する。", "anti_reframe_guard": "別基準へ逃げるのは別の問いだ。", "exception_policy": "単発例外では崩れない。", "burden_target": "Bは必要条件不成立を示す。"}},
                    "b": {},
                },
            },
            {
                "turn": 2,
                "a": "少なくとも短期なら成立する。",
                "b": "最初の条件と違う。",
                "meta": {
                    "a": {"drift_from_opening_contract": True, "scope_narrowing": True},
                    "b": {},
                },
            },
        ],
    )

    assert summary["weak_spot"]["label"] == "Contract drift"
    assert "opening contract" in summary["weak_spot"]["why_one_sentence"] or "後付け" in summary["weak_spot"]["why_one_sentence"]
    assert summary["why_axis_tag"] == "Contract drift"
    assert summary["winner_axis_tag"] == "Contract drift"


def test_sanitize_fighter_speech_removes_meta_leak_patterns():
    text = "相手の核心はそこじゃない。弱点は条件を足している点だ。話をずらしてるし、それは苦しい。"

    cleaned = _sanitize_fighter_speech(text)

    assert "相手の核心" not in cleaned
    assert "弱点は" not in cleaned
    assert "話をずらしてる" not in cleaned
    assert "それは苦しい" not in cleaned
    assert "相手の前提" in cleaned or "論点がずれている" in cleaned or "そのままでは通らない" in cleaned


def test_extract_transcript_quote_skips_meta_headline_and_picks_substantive_sentence():
    turns = [
        {
            "turn": 2,
            "a": "相手の核心はそこじゃない。金で買えるのは接触機会であって、自発的な愛情そのものではない。",
            "b": "",
        }
    ]

    quote, _ = _extract_transcript_quote(turns, 2, "A", "愛そのもの", "接触機会")

    assert quote == "金で買えるのは接触機会であって、自発的な愛情そのものではない。"


def test_normalize_summary_naturalizes_visible_meta_leakage_in_cards():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "相手の核心は崩れた。"},
            "reason_one_liner": "話をずらしてるBの押し込みはそのままでは通らない。",
            "fatal_phrase": {"turn": 2, "speaker": "B", "text": "金で買えるのは接触機会だ。", "reason": "弱点は条件論への逃げにある。"},
            "turning_point": {"turn": 2, "summary": "論点はこうだ。条件論へ逃げた瞬間に問いがずれた。", "quote_excerpt": "金で買えるのは接触機会だ。"},
            "weak_spot": {"side": "B", "turn": 2, "speaker": "B", "label": "問いの再発明", "quote_excerpt": "金で買えるのは接触機会だ。", "why_one_sentence": "相手の核心は本質ではなく条件に逃げた点だ。", "how_to_fix": "弱点は条件ではなく本質に答えることだった。"},
            "key_disagreement_top3": ["x"],
        },
        turns=[
            {"turn": 1, "a": "愛そのものが買えるかを問う。", "b": "金は環境を買える。"},
            {"turn": 2, "a": "条件の購入と愛そのものは違う。", "b": "金で買えるのは接触機会だ。"},
        ],
    )

    assert "相手の核心" not in summary["winner"]["reason"]
    assert "話をずらしてる" not in summary["reason_one_liner"]
    assert "弱点は" not in summary["fatal_phrase"]["reason"]
    assert "論点はこうだ" not in summary["turning_point"]["summary"]
    assert "相手の核心" not in summary["weak_spot"]["why_one_sentence"]


def test_mock_opening_and_rebuttal_sound_less_like_design_memo():
    result = run_debate(
        {
            "topic": "愛は金で買えるか",
            "side_a": "買えない。金で買えるのは接触機会や快適さであって、自発的な愛情そのものではない。",
            "side_b": "買える。愛は環境と継続的投資で成立する以上、金で成立条件を買える。",
            "turn_count": 3,
            "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        }
    )

    opening = result["debate"]["turns"][0]["a"]
    rebuttal = result["debate"]["turns"][1]["a"]

    assert "まずこの話は" not in opening
    assert "評価基準" not in opening
    assert "採用条件" not in opening
    assert "比較軸" not in opening
    assert "条件を並べることじゃなく" not in opening
    assert "舞台までで" in opening or "そのものが" in opening or "条件じゃなく" in opening or "そのものじゃない" in opening
    assert "相手は" in rebuttal or "相手が" in rebuttal
    assert "検証指標" not in rebuttal
    assert "副作用の条件が曖昧なまま止めている" not in rebuttal
    assert "問い自体がずれる" in rebuttal or "別の勝負になる" in rebuttal or "条件を丸ごと外すと" in rebuttal or "本題ではない" in rebuttal


def test_summary_structural_rewrite_avoids_design_memo_english_terms():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Aは opening contract の外へ出て主張範囲を後から守ろうとし、その drift が勝ち筋を弱くした。"},
            "reason_one_liner": "Aは最初に固定した comparison axis と acceptance condition の外へ出て、後付けの条件追加に見える返しになった。",
            "fatal_phrase": {"turn": 2, "speaker": "B", "text": "条件を足した時点で元の話から外れる。", "reason": "この一文でAの後付け条件が contract 外だと見えた。"},
            "turning_point": {"turn": 2, "summary": "Turn 2でAが contract 外へ出たため、争点が drift の有無に移った。", "quote_excerpt": "条件を足した時点で元の話から外れる。"},
            "weak_spot": {"side": "A", "turn": 2, "speaker": "A", "label": "Contract drift", "quote_excerpt": "条件を足した時点で元の話から外れる。", "why_one_sentence": "Aは opening contract の外へ主張範囲を動かし、精密化ではなく後付け防御と読まれた。", "how_to_fix": "最初に置いた基準を守るべきだった。"},
            "key_disagreement_top3": ["x"],
        },
        turns=[
            {"turn": 1, "a": "愛そのものが買えるかを問う。", "b": "金で条件を買える。"},
            {"turn": 2, "a": "少なくとも条件が整えば愛は成立する。", "b": "条件を足した時点で元の話から外れる。"},
        ],
    )

    joined = " ".join([
        summary["winner"]["reason"],
        summary["reason_one_liner"],
        summary["fatal_phrase"]["reason"],
        summary["turning_point"]["summary"],
        summary["weak_spot"]["why_one_sentence"],
    ])
    assert "opening contract" not in joined
    assert "comparison axis" not in joined
    assert "acceptance condition" not in joined
    assert "contract 外" not in joined


def test_normalize_summary_allows_b_win_when_b_breaks_lock_without_reframe():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが必要条件を壊した。"},
            "reason_one_liner": "Bは固定された採用条件の中でAの必要条件を壊した。",
            "turning_point": {"turn": 3, "summary": "Turn 3でBが必要条件の不成立を示した。", "quote_excerpt": "その条件は実例で成立しない。"},
            "fatal_phrase": {"turn": 3, "speaker": "B", "text": "その条件は実例で成立しない。", "reason": "Bが lock 内で必要条件を壊した。"},
            "weak_spot": {"side": "A", "turn": 3, "speaker": "A", "label": "論拠不足", "quote_excerpt": "その条件なら勝てる。", "why_one_sentence": "Aの必要条件が実例で崩れた。", "how_to_fix": "必要条件の実証を補強するべきだった。"},
            "key_disagreement_top3": ["x"],
        },
        turns=[
            {
                "turn": 1,
                "a": "この試合は採用条件で比べる。",
                "b": "その条件は実例で成立しない。",
                "meta": {
                    "a": {"proposition_lock": {"claim_subject": "採用条件", "claim_predicate": "成立するか", "comparison_unit": "命題そのもの", "evaluation_axis": "採用条件", "time_scope": "general_present", "quantifier_scope": "general_rule", "exception_policy": "例外で上書きしない", "means_vs_essence_lock": "essence_over_means", "proof_burden_shape": "必要条件の成立を示す", "forbidden_reframes": []}},
                    "b": {"proposition_lock": {"claim_subject": "採用条件", "claim_predicate": "成立するか", "comparison_unit": "命題そのもの", "evaluation_axis": "採用条件", "time_scope": "general_present", "quantifier_scope": "general_rule", "exception_policy": "例外で上書きしない", "means_vs_essence_lock": "essence_over_means", "proof_burden_shape": "必要条件の成立を示す", "forbidden_reframes": []}},
                },
            }
        ],
    )

    assert summary["reframe_detected"] is False
    assert summary["winner"]["side"] == "B"


def test_normalize_summary_seat_swap_does_not_force_b_win():
    a_as_owner = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが穴を突いた。"},
            "reason_one_liner": "Aは基準を維持したが、Bは寄生反論だけだった。",
            "turning_point": "Turn 4でAが『その反論は元の基準を壊していない』と返した。",
            "fatal_phrase": {"speaker": "A", "turn": 4, "text": "その反論は元の基準を壊していない。", "reason": "Aのフレームが残った。"},
            "weak_spot": {"side": "A", "turn": 4, "speaker": "A", "label": "論拠不足", "quote_excerpt": "まだ粗さはある。", "why_one_sentence": "Aには粗さがあるが、Bは必要条件を壊していない。", "how_to_fix": "残差を閉じるべきだった。"},
            "key_disagreement_top3": ["x"],
        }
    )
    b_as_owner = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが穴を突いた。"},
            "reason_one_liner": "Bは基準を維持したが、Aは寄生反論だけだった。",
            "turning_point": "Turn 4でBが『その反論は元の基準を壊していない』と返した。",
            "fatal_phrase": {"speaker": "B", "turn": 4, "text": "その反論は元の基準を壊していない。", "reason": "Bのフレームが残った。"},
            "weak_spot": {"side": "B", "turn": 4, "speaker": "B", "label": "論拠不足", "quote_excerpt": "まだ粗さはある。", "why_one_sentence": "Bには粗さがあるが、Aは必要条件を壊していない。", "how_to_fix": "残差を閉じるべきだった。"},
            "key_disagreement_top3": ["x"],
        }
    )

    assert a_as_owner["winner"]["side"] == "A"
    assert b_as_owner["winner"]["side"] == "B"


def test_normalize_summary_assigns_card_roles_and_separates_overlapping_cards():
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが勝った。"},
            "reason_one_liner": "Bが定義の後退を露出し、最後まで押し返した。",
            "turning_point": {
                "turn": 4,
                "summary": "Bが定義の後退を露出し、最後まで押し返した。",
                "quote_excerpt": "その定義は後から広げている。",
            },
            "fatal_phrase": {
                "turn": 4,
                "speaker": "B",
                "text": "その定義は後から広げている。",
                "reason": "Bが定義の後退を露出し、最後まで押し返した。",
            },
            "weak_spot": {
                "side": "A",
                "turn": 4,
                "speaker": "A",
                "label": "定義の後退",
                "quote_excerpt": "その定義は後から広げている。",
                "why_one_sentence": "Bが定義の後退を露出し、最後まで押し返した。",
                "how_to_fix": "条件を先に固定する。",
            },
            "gemini_quote": {
                "framing_text": "Bが定義の後退を露出し、最後まで押し返した。",
                "quote": "その定義は後から広げている。",
                "source_turn": 4,
                "source_side": "B",
            },
            "key_disagreement_top3": ["x"],
        },
        turns=[{"turn": 4, "a": "でもその定義は広げてよい。", "b": "その定義は後から広げている。"}],
    )

    assert summary["why_role"] == "verdict_summary"
    assert summary["fatal_phrase"]["role"] == "decisive_lock"
    assert summary["turning_point"]["role"] == "frame_shift"
    assert summary["weak_spot"]["role"] == "failure_exposure"
    assert summary["gemini_quote"]["framing_role"]
    assert summary["fatal_phrase"]["reason"] != summary["reason_one_liner"]
    assert summary["turning_point"]["summary"] != summary["reason_one_liner"]
    assert summary["weak_spot"]["why_one_sentence"] != summary["reason_one_liner"]
    assert summary["gemini_quote"]["framing_text"] != summary["reason_one_liner"]


def test_normalize_summary_separates_first_crack_decisive_lock_and_clincher():
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが最後に締めた。"},
            "reason_one_liner": "Aは早い段階でヒビを入れ、終盤で逃げ道を塞いだ。",
            "turning_point": {"turn": 3, "summary": "Turn 3で議論の軸が反例勝負へ移った。", "quote_excerpt": "その条件なら反例が残る。"},
            "fatal_phrase": {"turn": 4, "speaker": "A", "text": "その条件なら反例が残る。", "reason": "ここで勝ち筋が固定した。"},
            "weak_spot": {"side": "B", "turn": 2, "speaker": "B", "label": "論拠不足", "quote_excerpt": "前提だけではまだ弱い。", "why_one_sentence": "Bは前提を補強できず、最初の傷を残した。", "how_to_fix": "具体例を足すべきだった。"},
            "key_disagreement_top3": ["x"],
        },
        turns=[
            {"turn": 1, "a": "私はまず大枠の前提から入る。", "b": "その前提だけではまだ弱い。"},
            {"turn": 2, "a": "その前提だけではまだ弱い。", "b": "今の段階ではまだ証拠が足りない。"},
            {"turn": 3, "a": "その条件なら反例が残る。", "b": "それでも成立する。"},
            {"turn": 4, "a": "その条件なら反例が残る。", "b": "まだ一般論で守れる。"},
            {"turn": 5, "a": "最後までその反例に答えないなら、もう採れない。", "b": "最後は印象で押す。"},
        ],
    )

    assert summary["first_crack"]["role"] == "first_crack"
    assert summary["fatal_phrase"]["role"] == "decisive_lock"
    assert summary["clincher"]["role"] == "clincher"
    assert summary["first_crack"]["turn"] == 2
    assert summary["fatal_phrase"]["turn"] == 4
    assert summary["clincher"]["turn"] == 5
    assert summary["first_crack_turn"] == 2
    assert summary["decisive_lock_turn"] == 4
    assert summary["clincher_turn"] == 5
    assert summary["clincher"]["quote"]


def test_normalize_summary_allows_early_hit_without_promoting_it_to_decisive_lock():
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが終盤で取り切った。"},
            "reason_one_liner": "Aは序盤でヒビを入れたが、勝負を決めたのは終盤の詰めだった。",
            "turning_point": {"turn": 3, "summary": "Turn 3で論点が採用条件へ移った。", "quote_excerpt": "その条件だと維持できない。"},
            "fatal_phrase": {"turn": 5, "speaker": "A", "text": "その条件を最後まで守れないなら、もう採れない。", "reason": "ここで勝敗が固定した。"},
            "weak_spot": {"side": "B", "turn": 2, "speaker": "B", "label": "論拠不足", "quote_excerpt": "今の前提だけでは弱い。", "why_one_sentence": "Bに最初のヒビが入った。", "how_to_fix": "前提を補強するべきだった。"},
            "key_disagreement_top3": ["x"],
        },
        turns=[
            {"turn": 1, "a": "まず基準を置く。", "b": "その前提だけでは弱い。"},
            {"turn": 2, "a": "今の前提だけでは弱い。", "b": "まだ守れる。"},
            {"turn": 3, "a": "その条件だと維持できない。", "b": "条件を足せばよい。"},
            {"turn": 4, "a": "その追加条件は後付けだ。", "b": "まだ逃げ道はある。"},
            {"turn": 5, "a": "その条件を最後まで守れないなら、もう採れない。", "b": "そこまでは答え切れない。"},
        ],
    )

    assert summary["first_crack"]["turn"] == 2
    assert summary["fatal_phrase"]["turn"] == 5
    assert summary["fatal_phrase"]["role"] == "decisive_lock"


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

    quote = summary["gemini_quote"]["framing_text"]
    assert quote
    assert quote.startswith("「")
    assert "framing_role" in summary["gemini_quote"]
    assert "framing_reason" in summary["gemini_quote"]
    assert "evidence_quote" in summary["gemini_quote"]
    assert "evidence_turn" in summary["gemini_quote"]
    assert "evidence_side" in summary["gemini_quote"]


def test_normalize_summary_generated_gemini_quote_does_not_fake_transcript_anchor():
    summary = _normalize_summary(
        {
            "winner": {"side": "Draw", "reason": "拮抗した。"},
            "reason_one_liner": "決定打が出なかった。",
            "turning_point": "",
            "fatal_phrase": {"speaker": "", "turn": 0, "text": "", "reason": ""},
            "weak_spot": {"side": "", "turn": 0, "speaker": "", "label": "", "quote_excerpt": "", "why_one_sentence": "", "how_to_fix": ""},
            "gemini_quote": {"text": "基準を握った側が議論を支配する。"},
        },
        [],
    )

    assert summary["gemini_quote"]["evidence_quote"] == ""
    assert summary["gemini_quote"]["evidence_turn"] == 0
    assert summary["gemini_quote"]["evidence_side"] == ""
    assert summary["gemini_quote"]["debug_source"] == "generated_fallback"
    assert summary["gemini_quote"]["verdict_consistency"] is True


def test_extract_turn_speech_ignores_unhashable_speaker_shape():
    from tools.debate_api import _extract_turn_speech

    turns = [{"turn": 2, "a": "A側の本文。", "b": "B側の本文。"}]

    assert _extract_turn_speech(turns, 2, ["A"]) == ""
    assert _extract_turn_speech(turns, 2, {"speaker": "A"}) == ""


def test_normalize_summary_degrades_instead_of_raising_on_malformed_anchor_shapes():
    turns = [{"turn": 2, "a": "A側の本文。", "b": "B側の本文。"}]

    summary = _normalize_summary(
        {
            "winner": "B",
            "reason_one_liner": None,
            "fatal_phrase": {"turn": "x", "speaker": ["A"], "text": {"k": "v"}, "reason": ["r"]},
            "turning_point": {"turn": "x", "quote_excerpt": ["bad"], "summary": ["weird"]},
            "weak_spot": {
                "side": ["A"],
                "turn": ["x"],
                "speaker": {"a": 1},
                "label": ["x"],
                "quote_excerpt": {"q": 1},
                "why_one_sentence": ["y"],
                "how_to_fix": ["z"],
            },
            "gemini_quote": {"text": ["g"], "source_turn": ["2"], "source_side": ["A"], "quote": {"a": 1}},
        },
        turns,
    )

    assert summary["fatal_phrase"]["quote"] == ""
    assert isinstance(summary["turning_point"], dict)
    assert "summary" in summary["turning_point"]
    assert isinstance(summary["weak_spot"], dict)
    assert "quote_excerpt" in summary["weak_spot"]
    assert isinstance(summary["gemini_quote"], dict)
    assert "text" in summary["gemini_quote"]


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


def test_normalize_summary_rejects_gemini_quote_that_reads_against_locked_winner():
    turns = [
        {"turn": 1, "a": "陰謀論と呼ばれていた時期でも、証拠はあった。", "b": "それは検証可能な証拠ではない。"},
        {"turn": 2, "a": "分類が遅れただけで、真実は混ざっていた。", "b": "真実があるなら、陰謀論ではなく検証可能な仮説として残る。"},
    ]
    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが押した。"},
            "reason_one_liner": "Bは『証拠があるなら陰謀論ではなく仮説として残る』と基準を固定した。",
            "turning_point": {"turn": 2, "summary": "Turn 2でBが検証可能性を争点として固定した。", "quote_excerpt": "真実があるなら、陰謀論ではなく検証可能な仮説として残る。"},
            "fatal_phrase": {"turn": 2, "speaker": "B", "text": "真実があるなら、陰謀論ではなく検証可能な仮説として残る。", "reason": "Bが分類ではなく検証可能性へ基準を戻した。"},
            "weak_spot": {"side": "A", "turn": 1, "speaker": "A", "label": "論拠不足", "quote_excerpt": "陰謀論と呼ばれていた時期でも、証拠はあった。", "why_one_sentence": "Aは存在主張をしたが、検証可能性を出せなかった。", "how_to_fix": "証拠の検証経路を先に示すべきだった。"},
            "gemini_quote": {"text": "陰謀論と呼ばれていた時期でも、証拠はあった。", "source_turn": 1, "source_side": "A"},
        },
        turns,
    )

    assert summary["gemini_quote"]["evidence_quote"] != "陰謀論と呼ばれていた時期でも、証拠はあった。"
    assert summary["gemini_quote"]["evidence_side"] == "B"
    assert summary["gemini_quote"]["verdict_consistency"] is True
    assert summary["gemini_quote"]["consistency_reason"] in {"supported_by_why_fatal_weak", "winner_aligned_sentence", "aligned_with_decisive_frame"}


def test_normalize_summary_rejects_fragmentary_gemini_quote_and_expands_to_complete_sentence():
    turns = [
        {"turn": 2, "a": "Watergateは当時ただの疑惑ではなく、証拠が積み上がっていた。", "b": "それは事後的に整理されただけだ。"},
    ]
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが押した。"},
            "reason_one_liner": "Aは具体例が当時の検証可能性を満たしていたと示した。",
            "turning_point": {"turn": 2, "summary": "Turn 2でWatergateの例が象徴になった。"},
            "fatal_phrase": {"turn": 2, "speaker": "A", "text": "Watergateは当時ただの疑惑ではなく、証拠が積み上がっていた。", "reason": "当時の検証可能性を示した。"},
            "weak_spot": {"side": "B", "turn": 2, "speaker": "B", "label": "論拠不足", "quote_excerpt": "それは事後的に整理されただけだ。", "why_one_sentence": "Bは当時点の証拠水準に返せなかった。", "how_to_fix": "当時検証できなかった根拠を示すべきだった。"},
            "gemini_quote": {"text": "Watergateは当時。", "source_turn": 2, "source_side": "A"},
        },
        turns,
    )

    assert summary["gemini_quote"]["evidence_quote"] == "Watergateは当時ただの疑惑ではなく、証拠が積み上がっていた。"
    assert "Watergateは当時。" not in summary["gemini_quote"]["framing_text"]
    assert summary["gemini_quote"]["verdict_consistency"] is True


def test_normalize_summary_expands_display_text_for_mk_ultra_fragment():
    turns = [
        {
            "turn": 3,
            "a": "MKウルトラもスノーデン文書も、国家が実際に秘密裏の工作を行った証拠として残っている。",
            "b": "個別事件の存在は、陰謀論全体の真実性を保証しない。",
        },
    ]
    summary = _normalize_summary(
        {
            "winner": {"side": "A", "reason": "Aが押した。"},
            "reason_one_liner": "Aは個別の実証例を出して、全面否定を止めた。",
            "turning_point": {"turn": 3, "summary": "Turn 3で具体例が一般否定を止めた。"},
            "fatal_phrase": {"turn": 3, "speaker": "A", "text": "MKウルトラもスノーデン文書も、国家が実際に秘密裏の工作を行った証拠として残っている。", "reason": "具体例で全面否定を止めた。"},
            "weak_spot": {"side": "B", "turn": 3, "speaker": "B", "label": "論拠不足", "quote_excerpt": "個別事件の存在は、陰謀論全体の真実性を保証しない。", "why_one_sentence": "Bは例外と構造の切り分けはしたが、全面否定を維持できなかった。", "how_to_fix": "どこまでを陰謀論に含めるかの線引きを先に示すべきだった。"},
            "gemini_quote": {"text": "MKウルトラもスノーデン文書も。", "source_turn": 3, "source_side": "A"},
        },
        turns,
    )

    assert summary["gemini_quote"]["evidence_quote"] == "MKウルトラもスノーデン文書も、国家が実際に秘密裏の工作を行った証拠として残っている。"
    assert "実証例" in summary["gemini_quote"]["framing_text"] or "全面否定" in summary["gemini_quote"]["framing_text"]
    assert summary["gemini_quote"]["framing_text"].startswith("「")


def test_normalize_summary_splits_gemini_quote_into_framing_and_evidence_layers():
    turns = [
        {"turn": 1, "a": "Aは事件が後から真実だと分かった例を並べた。", "b": "Bはそれを分類の問題だと返した。"},
        {"turn": 2, "a": "相手は『文書・証言・検証可能な連鎖で暴かれる』から陰謀論じゃないと言うが。", "b": "Bは『証明後にラベルを外す操作』自体を封じ、問いを固定した。"},
    ]

    summary = _normalize_summary(
        {
            "winner": {"side": "B", "reason": "Bが問いの定義を固定した。"},
            "reason_one_liner": "Bは『証明後にラベルを外す』操作を封じ、問いを固定した。",
            "confidence": "High",
            "turning_point": {"turn": 2, "summary": "Bが問いを固定した。", "quote_excerpt": "Bは『証明後にラベルを外す操作』自体を封じ、問いを固定した。"},
            "fatal_phrase": {"turn": 2, "speaker": "B", "text": "Bは『証明後にラベルを外す操作』自体を封じ、問いを固定した。", "reason": "定義のすり替えを封じた。"},
            "weak_spot": {"side": "A", "turn": 2, "speaker": "A", "label": "定義の後退", "quote_excerpt": "相手は『文書・証言・検証可能な連鎖で暴かれる』から陰謀論じゃないと言うが。", "why_one_sentence": "Aは後からラベルを外す論法に寄りかかった。", "how_to_fix": "問いの定義を先に固定するべきだった。"},
            "gemini_quote": {"text": "相手は『文書・証言・検証可能な連鎖で暴かれる』から陰謀論じゃないと言うが。", "source_turn": 2, "source_side": "A"},
        },
        turns,
    )

    gemini_quote = summary["gemini_quote"]
    assert gemini_quote["framing_text"].startswith("「")
    assert "問い" in gemini_quote["framing_text"] or "固定" in gemini_quote["framing_text"]
    assert gemini_quote["evidence_quote"]
    assert gemini_quote["evidence_turn"] in {1, 2}
    assert gemini_quote["evidence_side"] in {"A", "B"}
    assert gemini_quote["framing_role"]
    assert gemini_quote["framing_reason"]
    assert gemini_quote["text"] == gemini_quote["framing_text"]
    assert gemini_quote["quote"] == gemini_quote["evidence_quote"]


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
    assert any(word in literature for word in ["動かなかった", "立たなかった", "崩れた", "残った", "ならない"])


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
