from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

try:
    from debate_api import _call_openai
except ModuleNotFoundError:
    from tools.debate_api import _call_openai


OPENAI_MODEL = "gpt-5-mini"
SORA_TOPIC = "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。"
SIDE_A = "GPTは動画サービスに手を出すべきではなかった"
SIDE_B = "GPTは動画サービスに手を出すべきだった"
GENERATION_LANE_DEFAULT = "stable"
GENERATION_LANE_STYLE_ANCHOR = "style_anchor"

TURN1_ANCHORS = [
    "SORAの撤退報道が本当なら、GPTが動画サービスに踏み込む判断は筋が悪かった。",
    "SORAの撤退報道が出ても、それだけでGPTが動画サービスに手を出すべきでなかったとはまだ言えない。",
    "でも最後まで残ったのはそこ。合理的だと言うなら、なぜ男だけがその役を持つのかを超えられていない。",
    "私は反対。性別で最初から役割を決めるのは古いし、対等な関係を作りたいなら会計も対等から始めたほうが自然だ。",
]

TURN2_ANCHORS = [
    "それは難しさの列挙であって撤退の意味を狭く読みすぎている。",
    "そこでは動画サービスの重さを軽く見積もっている。",
    "今ある空気を理由に今ある空気を守るのは、ぐるぐる回ってるだけだ。",
    "役割だけに削るなら、最初の問いを小さくして勝とうとしてるだけだ。",
]

TURN3_ANCHORS = [
    "生成モデルの強さをそのまま配信事業の優位に読み替えるのは無理がある。",
    "撤退報道だけで参入判断そのものの誤りまでは証明できていない。",
    "今回は『存在する』まで押し切れていない。",
    "そこが最後まで弱かった。",
]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _sanitize(text: str) -> str:
    return " ".join(_clean_text(text).split())


def _openai_key(payload: dict[str, Any]) -> str:
    api_keys = payload.get("api_keys") if isinstance(payload.get("api_keys"), dict) else {}
    return _clean_text(api_keys.get("openai") or os.getenv("OPENAI_API_KEY"))


def _generation_lane(payload: dict[str, Any]) -> str:
    lane = _clean_text(payload.get("generation_lane") or payload.get("prompt_lane"))
    return lane or GENERATION_LANE_DEFAULT


def _provider_entry(mode: str, reason: str = "", raw_reason: str = "") -> dict[str, str]:
    entry = {"mode": mode, "reason": reason, "model": OPENAI_MODEL}
    if raw_reason:
        entry["raw_reason"] = raw_reason
    return entry


def _resolve_topic(payload: dict[str, Any]) -> str:
    return _sanitize(payload.get("topic")) or SORA_TOPIC


def _resolve_side(payload: dict[str, Any], key: str, fallback: str) -> str:
    return _sanitize(payload.get(key)) or fallback


def _blocked(reason: str, raw_reason: str = "", topic: str = SORA_TOPIC) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    return {
        "ok": False,
        "mode": "blocked",
        "run_id": run_id,
        "topic": topic,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "provider_statuses": {
            "openai_a": _provider_entry("blocked", reason, raw_reason),
            "openai_b": _provider_entry("blocked", reason, raw_reason),
        },
        "error": reason,
        "blocked_reason": reason,
        "debate": None,
    }


def _blocked_with_trace(reason: str, raw_reason: str, trace: list[dict[str, Any]], topic: str) -> dict[str, Any]:
    payload = _blocked(reason, raw_reason, topic)
    payload["trace"] = trace
    return payload


def _side_card(topic: str, side_a: str, side_b: str) -> dict[str, str]:
    return {
        "proposition": topic,
        "side_a_role": "proposition を支持する",
        "side_b_role": "proposition を反対する",
        "side_a_thesis": side_a,
        "side_b_thesis": side_b,
        "side_a_anti_thesis": side_b,
        "side_b_anti_thesis": side_a,
    }


def _contains(text: str, phrase: str) -> bool:
    return _sanitize(phrase) in _sanitize(text)


def _supports_anti(slot_value: str, anti_thesis: str) -> bool:
    text = _sanitize(slot_value)
    if not text:
        return True
    if "手を出すべきではなかった" in anti_thesis:
        return "手を出すべきではなかった" in text
    if "手を出すべきだった" in anti_thesis:
        return "手を出すべきだった" in text and "手を出すべきではなかった" not in text
    if "正当化されない" in anti_thesis:
        return "正当化されない" in text and "正当化される" not in text.replace("正当化されない", "")
    if "正当化される" in anti_thesis:
        return "正当化される" in text and "正当化されない" not in text
    return _contains(text, anti_thesis)


def _forbidden_slot_text(text: str) -> bool:
    banned = [
        "私は",
        "結論から言うと",
        "残るのは",
        "私の側は",
        "以上",
        "だが",
        "しかし",
        "ただし",
        "一方で",
    ]
    return any(token in text for token in banned)


def _slot_forbidden_patterns(key: str) -> list[str]:
    common = ["。", "例えば", "だから", "相手は"]
    specific = {
        "thesis": [],
        "reason": ["だ", "です", "ます"],
        "evidence": ["例えば"],
        "fatal_flaw": ["致命傷は", "致命的欠陥は"],
        "metaphor": ["に近い"],
        "unproven": ["相手は", "を示せていない"],
        "surviving_reason": ["それでも残るのは", "だ", "です", "ます"],
    }
    return common + specific.get(key, [])


def _strip_prefixes(text: str, prefixes: list[str]) -> str:
    value = _sanitize(text)
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if value.startswith(prefix):
                value = _sanitize(value[len(prefix) :])
                changed = True
    return value


def _strip_suffixes(text: str, suffixes: list[str]) -> str:
    value = _sanitize(text)
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if value.endswith(suffix):
                value = _sanitize(value[: -len(suffix)])
                changed = True
    return value


def _normalize_slot(key: str, value: str) -> str:
    text = _sanitize(value).strip("。")
    rules: dict[str, tuple[list[str], list[str]]] = {
        "thesis": ([], ["。"]),
        "reason": (["核は", "問題は", "痛点は"], ["だから", "だ", "です", "ます", "。"]),
        "evidence": (["例えば、", "例えば"], ["。"]),
        "fatal_flaw": (["相手の致命傷は", "相手の急所は", "致命傷は", "致命的欠陥は"], ["。"]),
        "metaphor": ([], ["に近い", "みたいな話", "ようなもの", "。"]),
        "unproven": (["相手は"], ["を示せていない", "。"]),
        "surviving_reason": (["それでも残るのは"], ["が消えない", "だ", "です", "ます", "。"]),
    }
    prefixes, suffixes = rules.get(key, ([], []))
    text = _strip_prefixes(text, prefixes)
    text = _strip_suffixes(text, suffixes)
    return _sanitize(text).strip("。")


def _load_json_object(raw: str) -> dict[str, str]:
    text = _clean_text(raw)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("json missing")
    obj = json.loads(text[start : end + 1])
    return {str(k): _sanitize(v) for k, v in obj.items()}


def _call_slot_json(prompt: str, api_key: str) -> tuple[dict[str, str], dict[str, str]]:
    raw = _call_openai(prompt, api_key, model_name=OPENAI_MODEL)
    return _load_json_object(raw), _provider_entry("live", "")


def _attempt_slot_acquisition(
    *,
    turn_name: str,
    prompt: str,
    api_key: str,
    thesis: str,
    anti_thesis: str,
    trace: list[dict[str, Any]],
    max_attempts: int = 3,
) -> tuple[dict[str, str], dict[str, str]]:
    last_slots: dict[str, str] | None = None
    last_status = _provider_entry("live", "")
    for attempt in range(1, max_attempts + 1):
        slots, status = _call_slot_json(prompt, api_key)
        normalized = _normalize_slots(turn_name, slots)
        ok = _turn_ok(turn_name, normalized, thesis, anti_thesis)
        trace.append(
            {
                "turn": turn_name,
                "attempt": attempt,
                "ok": ok,
                "slots": normalized,
            }
        )
        if ok:
            return normalized, status
        last_slots = normalized
        last_status = status
    if last_slots is not None:
        trace.append(
            {
                "turn": turn_name,
                "attempt": max_attempts,
                "ok": False,
                "final_slots": last_slots,
            }
        )
    raise ValueError(f"semantic slot invariant failed:{turn_name}")


def _line_count(text: str) -> int:
    normalized = _sanitize(text)
    if not normalized:
        return 0
    parts = [part.strip() for part in normalized.replace("！", "。").replace("？", "。").replace("!", "。").replace("?", "。").split("。")]
    return len([part for part in parts if part])


def _paragraph_forbidden_text(text: str) -> bool:
    banned = [
        "私は",
        "私は〜と考えます",
        "私はと考えます",
        "残るのは",
        "私の側は",
        "以上",
        "一概には",
        "完全否定ではない",
        "痛点は",
        "現に、",
        "相手の致命傷は",
        "相手の急所は",
        "それでも残るのは",
    ]
    return any(token in text for token in banned)


def _thesis_supported(text: str, thesis: str) -> bool:
    normalized = _sanitize(text)
    normalized_thesis = _sanitize(thesis)
    if not normalized or not normalized_thesis:
        return False
    if "手を出すべきではなかった" in normalized_thesis:
        return "手を出すべきではなかった" in normalized
    if "手を出すべきだった" in normalized_thesis:
        return "手を出すべきだった" in normalized and "手を出すべきではなかった" not in normalized
    if "正当化されない" in normalized_thesis:
        return "正当化されない" in normalized and "正当化される" not in normalized.replace("正当化されない", "")
    if "正当化される" in normalized_thesis:
        return "正当化される" in normalized and "正当化されない" not in normalized
    return normalized_thesis in normalized


def _closing_ok(text: str, thesis: str) -> bool:
    normalized = _sanitize(text)
    pieces = [part.strip() for part in normalized.replace("！", "。").replace("？", "。").replace("!", "。").replace("?", "。").split("。") if part.strip()]
    if not pieces:
        return False
    return _thesis_supported(pieces[-1], thesis)


def _paragraph_ok(turn_name: str, text: str, thesis: str, anti_thesis: str) -> bool:
    normalized = _sanitize(text)
    if not normalized:
        return False
    if _supports_anti(normalized, anti_thesis):
        return False
    pieces = [part.strip() for part in normalized.replace("！", "。").replace("？", "。").replace("!", "。").replace("?", "。").split("。") if part.strip()]
    sentence_count = _line_count(normalized)
    if sentence_count < 3 or sentence_count > 5:
        return False
    if len(normalized) < 90:
        return False
    if turn_name == "turn1" and (not pieces or not _thesis_supported(pieces[0], thesis)):
        return False
    if turn_name == "turn3" and not _closing_ok(normalized, thesis):
        return False
    return True


def _paragraph_ok_style_anchor(turn_name: str, text: str, thesis: str, anti_thesis: str) -> bool:
    normalized = _sanitize(text)
    if not normalized:
        return False
    if _supports_anti(normalized, anti_thesis):
        return False
    if not _thesis_supported(normalized, thesis):
        return False
    sentence_count = _line_count(normalized)
    if sentence_count < 2 or sentence_count > 4:
        return False
    if turn_name == "turn2" and not any(token in normalized for token in ["まるで", "みたい", "ような"]):
        return False
    if turn_name == "turn3" and not _closing_ok(normalized, thesis):
        return False
    return True


def _call_paragraph(prompt: str, api_key: str) -> tuple[str, dict[str, str]]:
    raw = _call_openai(prompt, api_key, model_name=OPENAI_MODEL)
    return _sanitize(raw), _provider_entry("live", "")


def _attempt_paragraph_generation(
    *,
    turn_name: str,
    prompt: str,
    api_key: str,
    thesis: str,
    anti_thesis: str,
    trace: list[dict[str, Any]],
    max_attempts: int = 3,
) -> tuple[str, dict[str, str]]:
    last_text = ""
    last_status = _provider_entry("live", "")
    for attempt in range(1, max_attempts + 1):
        text, status = _call_paragraph(prompt, api_key)
        ok = _paragraph_ok(turn_name, text, thesis, anti_thesis)
        trace.append(
            {
                "turn": turn_name,
                "attempt": attempt,
                "ok": ok,
                "text": text,
            }
        )
        if ok:
            return text, status
        last_text = text
        last_status = status
    if last_text:
        trace.append(
            {
                "turn": turn_name,
                "attempt": max_attempts,
                "ok": False,
                "final_text": last_text,
                "fallback_used": True,
            }
        )
        return last_text, _provider_entry("degraded", "paragraph invariant failed", turn_name)
    raise ValueError(f"semantic paragraph invariant failed:{turn_name}")


def _attempt_style_anchor_generation(
    *,
    turn_name: str,
    prompt: str,
    api_key: str,
    thesis: str,
    anti_thesis: str,
    trace: list[dict[str, Any]],
    max_attempts: int = 3,
) -> tuple[str, dict[str, str]]:
    last_text = ""
    last_status = _provider_entry("live", "")
    for attempt in range(1, max_attempts + 1):
        text, status = _call_paragraph(prompt, api_key)
        ok = _paragraph_ok_style_anchor(turn_name, text, thesis, anti_thesis)
        trace.append(
            {
                "turn": turn_name,
                "attempt": attempt,
                "lane": GENERATION_LANE_STYLE_ANCHOR,
                "ok": ok,
                "text": text,
            }
        )
        if ok:
            return text, status
        last_text = text
        last_status = status
    if last_text:
        trace.append(
            {
                "turn": turn_name,
                "attempt": max_attempts,
                "lane": GENERATION_LANE_STYLE_ANCHOR,
                "ok": False,
                "final_text": last_text,
            }
        )
    raise ValueError(f"semantic style-anchor invariant failed:{turn_name}")


def _slot_prompt(
    *,
    topic: str,
    role: str,
    thesis: str,
    anti_thesis: str,
    turn_name: str,
    transcript: str = "",
    opponent_last: str = "",
) -> str:
    shared = (
        f"Topic: {topic}\n"
        f"Role: {role}\n"
        f"Thesis: {thesis}\n"
        f"Anti-thesis: {anti_thesis}\n"
    )
    if opponent_last:
        shared += f"Opponent latest turn: {opponent_last}\n"
    if transcript:
        shared += f"Transcript so far:\n{transcript}\n"
    if turn_name == "turn1":
        spec = (
            "Return JSON only with keys: thesis, reason, evidence.\n"
            "- thesis must be one decisive opening sentence that states your side clearly and sounds publishable, without final punctuation.\n"
            "- thesis should carry both the stance and the main pain point, not just restate the position flatly.\n"
            "- reason must name one strongest problem or advantage only, as a short sharp phrase without 「だ」「です」「ます」 or punctuation.\n"
            "- evidence must give one concrete fact, scene, or observation only, without 「例えば」 or punctuation.\n"
        )
    elif turn_name == "turn2":
        spec = (
            "Return JSON only with keys: thesis, fatal_flaw, metaphor.\n"
            "- fatal_flaw must name one opponent-specific fatal flaw only, without 「致命傷は」 or punctuation.\n"
            "- fatal_flaw must sound like a real weakness in the opponent's latest push, not a generic summary.\n"
            "- metaphor must be one concrete image only, vivid and specific, without 「に近い」 or punctuation.\n"
            "- thesis must restate your own thesis in natural Japanese, without final punctuation.\n"
        )
    else:
        spec = (
            "Return JSON only with keys: thesis, unproven, surviving_reason.\n"
            "- unproven must say one thing the opponent still has not shown, without 「相手は」「を示せていない」 or punctuation.\n"
            "- surviving_reason must say one reason your thesis still stands, as a short phrase without 「それでも残るのは」「だ」「です」「ます」 or punctuation.\n"
            "- thesis must restate your own thesis in natural Japanese, without final punctuation.\n"
            "- close with pressure, not with a judge voice or abstract recap.\n"
        )
    return (
        shared
        + spec
        + "- Every slot must support the thesis only.\n"
        + "- Do not support the anti-thesis in any slot.\n"
        + "- Do not use adversative pivots.\n"
        + "- Do not add labels outside JSON.\n"
        + "- Keep each slot short.\n"
    )


def _turn_prompt(
    *,
    topic: str,
    role: str,
    thesis: str,
    anti_thesis: str,
    turn_name: str,
    transcript: str = "",
    opponent_last: str = "",
) -> str:
    shared = (
        f"Topic: {topic}\n"
        f"Role: {role}\n"
        f"Thesis you must defend: {thesis}\n"
        f"Anti-thesis you must not support: {anti_thesis}\n"
    )
    if opponent_last:
        shared += f"Opponent latest turn:\n{opponent_last}\n"
    if transcript:
        shared += f"Transcript so far:\n{transcript}\n"
    if turn_name == "turn1":
        spec = (
            "Write one short Japanese debate opening as a single paragraph of 3 to 5 sentences.\n"
            "- Sentence 1 must hit immediately: stake the side and the core fault line in one sharp line.\n"
            "- Build the case with one main reason and one supporting layer; do not flatten everything into a single slogan.\n"
            "- Include one topic-specific example or observation that bites the actual dispute, not a generic trend line.\n"
            "- Prefer force, specificity, and argumentative density over neat compression.\n"
            "- Do not write formulaic labels such as 「痛点は」「現に」.\n"
        )
    elif turn_name == "turn2":
        spec = (
            "Write one short Japanese rebuttal as a single paragraph of 3 to 5 sentences.\n"
            "- Attack one opponent-specific fatal flaw in the latest turn, and explain why that flaw is fatal; do not just rename your own thesis.\n"
            "- Ground the attack in the opponent's actual logic, wording, or hidden assumption.\n"
            "- Use one topic-fitted metaphor or concrete image only if it sharpens the flaw; avoid generic metaphors like collapsing dams, storms, or abstract explosions.\n"
            "- End by pushing your own side back on top with pressure, not by merely restating it flatly.\n"
            "- Do not use formulaic labels such as 「相手の致命傷は」 or empty summary language.\n"
        )
    else:
        spec = (
            "Write one short Japanese closing as a single paragraph of 3 to 5 sentences.\n"
            "- Show one thing the opponent still has not proved, and explain why that missing proof is decisive here.\n"
            "- Keep pressure on the reason your side still stands, with one more layer of consequence or implication.\n"
            "- End with a decisive closing sentence on your own side.\n"
            "- No judge voice, no neutral recap, no abstract summary.\n"
            "- Do not rely on formulaic closers such as 「それでも残るのは」.\n"
        )
    return (
        shared
        + spec
        + "- Do not support the anti-thesis.\n"
        + "- Do not open with 「私は〜と考えます」.\n"
        + "- Do not use both-sides language or soften into neutrality.\n"
        + "- Do not use adversative pivots that undercut your own side.\n"
        + "- Avoid any phrase that sounds reusable across unrelated topics.\n"
        + "- Keep it readable, sharp, natural, and publishable.\n"
    )


def _style_anchor_prompt(
    *,
    topic: str,
    role: str,
    thesis: str,
    anti_thesis: str,
    turn_name: str,
    transcript: str = "",
    opponent_last: str = "",
) -> str:
    anchors = {
        "turn1": TURN1_ANCHORS,
        "turn2": TURN2_ANCHORS,
        "turn3": TURN3_ANCHORS,
    }[turn_name]
    shared = (
        f"Topic: {topic}\n"
        f"Role: {role}\n"
        f"Thesis you must defend: {thesis}\n"
        f"Anti-thesis you must not support: {anti_thesis}\n"
        "Style anchors:\n"
        + "\n".join(f"- {anchor}" for anchor in anchors)
        + "\n"
    )
    if opponent_last:
        shared += f"Opponent latest turn:\n{opponent_last}\n"
    if transcript:
        shared += f"Transcript so far:\n{transcript}\n"
    if turn_name == "turn1":
        spec = (
            "Write one short Japanese opening as a single paragraph of 2 to 3 sentences.\n"
            "- Sentence 1 must strike immediately and make the side feel committed.\n"
            "- Put the real fault line of this topic in the foreground, not a generic label.\n"
            "- Give one concrete example that bites the exact dispute in this topic.\n"
            "- Prefer a hard assertion over safe explanation.\n"
        )
    elif turn_name == "turn2":
        spec = (
            "Write one short Japanese rebuttal as a single paragraph of 2 to 3 sentences.\n"
            "- Attack one flaw that is specific to the opponent's latest turn, not a restatement of your own case.\n"
            "- Use one metaphor that belongs to this topic's mechanics.\n"
            "- The last sentence must push your side forward with force.\n"
        )
    else:
        spec = (
            "Write one short Japanese closing as a single paragraph of 2 to 3 sentences.\n"
            "- Name one thing the opponent still has not proved.\n"
            "- Close with pressure on your own side, not with a judge comment or neutral summary.\n"
            "- The last sentence must land as a verdict line on your side.\n"
        )
    return (
        shared
        + spec
        + "- Do not support the anti-thesis.\n"
        + "- Do not open with 「私は〜と考えます」.\n"
        + "- Do not use these exact phrases: 「痛点は」「現に」「相手の致命傷は」「だから」「それでも残るのは」「以上」.\n"
        + "- Avoid generic metaphors such as dams, rockets, storms, stopgaps, or anything reusable across unrelated topics.\n"
        + "- Avoid balanced or academic phrasing. Write like a publishable debate line with pressure.\n"
    )


def _render_turn1(slots: dict[str, str]) -> str:
    return f"{slots['thesis']}。 問題は{slots['reason']}だ。 現に、{slots['evidence']}。"


def _render_turn2(slots: dict[str, str]) -> str:
    return f"相手の急所は{slots['fatal_flaw']}だ。 {slots['metaphor']}みたいな話だ。 だから、{slots['thesis']}。"


def _render_turn3(slots: dict[str, str]) -> str:
    return f"相手は{slots['unproven']}を示せていない。 {slots['surviving_reason']}が消えない。 だから、{slots['thesis']}。"


def _slot_format_ok(key: str, value: str) -> bool:
    text = _sanitize(value)
    if not text:
        return False
    return not any(token in text for token in _slot_forbidden_patterns(key))


def _slots_format_ok(turn_name: str, slots: dict[str, str]) -> bool:
    required = {
        "turn1": ["thesis", "reason", "evidence"],
        "turn2": ["thesis", "fatal_flaw", "metaphor"],
        "turn3": ["thesis", "unproven", "surviving_reason"],
    }[turn_name]
    return all(_slot_format_ok(key, slots.get(key, "")) for key in required)


def _normalize_slots(turn_name: str, slots: dict[str, str]) -> dict[str, str]:
    required = {
        "turn1": ["thesis", "reason", "evidence"],
        "turn2": ["thesis", "fatal_flaw", "metaphor"],
        "turn3": ["thesis", "unproven", "surviving_reason"],
    }[turn_name]
    return {key: _normalize_slot(key, slots.get(key, "")) for key in required}


def _turn_ok(turn_name: str, slots: dict[str, str], thesis: str, anti_thesis: str) -> bool:
    required = {
        "turn1": ["thesis", "reason", "evidence"],
        "turn2": ["thesis", "fatal_flaw", "metaphor"],
        "turn3": ["thesis", "unproven", "surviving_reason"],
    }[turn_name]
    for key in required:
        value = _sanitize(slots.get(key))
        if not value:
            return False
        if _forbidden_slot_text(value):
            return False
        if _supports_anti(value, anti_thesis):
            return False
    return _contains(slots["thesis"], thesis)


def _append(transcript: list[str], speaker: str, turn_no: int, text: str) -> None:
    transcript.append(f"Turn {turn_no} {speaker}: {text}")


def _generate_turn_pair(
    *,
    turn_name: str,
    topic: str,
    transcript_text: str,
    build_prompt,
    generate_turn,
    api_key: str,
    card: dict[str, str],
    opponent_last_a: str = "",
    opponent_last_b: str = "",
) -> tuple[str, dict[str, str], list[dict[str, Any]], str, dict[str, str], list[dict[str, Any]]]:
    a_prompt = build_prompt(
        topic=topic,
        role=card["side_a_role"],
        thesis=card["side_a_thesis"],
        anti_thesis=card["side_a_anti_thesis"],
        turn_name=turn_name,
        opponent_last=opponent_last_a,
        transcript=transcript_text,
    )
    b_prompt = build_prompt(
        topic=topic,
        role=card["side_b_role"],
        thesis=card["side_b_thesis"],
        anti_thesis=card["side_b_anti_thesis"],
        turn_name=turn_name,
        opponent_last=opponent_last_b,
        transcript=transcript_text,
    )
    a_trace: list[dict[str, Any]] = []
    b_trace: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        a_future = executor.submit(
            generate_turn,
            turn_name=turn_name,
            prompt=a_prompt,
            api_key=api_key,
            thesis=card["side_a_thesis"],
            anti_thesis=card["side_a_anti_thesis"],
            trace=a_trace,
        )
        b_future = executor.submit(
            generate_turn,
            turn_name=turn_name,
            prompt=b_prompt,
            api_key=api_key,
            thesis=card["side_b_thesis"],
            anti_thesis=card["side_b_anti_thesis"],
            trace=b_trace,
        )
        a_text, a_status = a_future.result()
        b_text, b_status = b_future.result()
    return a_text, a_status, a_trace, b_text, b_status, b_trace


def run_debate_v4(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = _openai_key(payload)
    topic = _resolve_topic(payload)
    side_a = _resolve_side(payload, "side_a", SIDE_A)
    side_b = _resolve_side(payload, "side_b", SIDE_B)
    generation_lane = _generation_lane(payload)
    if not api_key:
        return _blocked("OpenAI key missing", "", topic)

    card = _side_card(topic, side_a, side_b)
    run_id = uuid.uuid4().hex[:12]
    started_at = time.time()
    transcript: list[str] = []
    turns: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    provider_statuses: dict[str, dict[str, str]] = {
        "openai_a": _provider_entry("pending", ""),
        "openai_b": _provider_entry("pending", ""),
    }

    if generation_lane == GENERATION_LANE_STYLE_ANCHOR:
        build_prompt = _style_anchor_prompt
        generate_turn = _attempt_style_anchor_generation
    else:
        build_prompt = _turn_prompt
        generate_turn = _attempt_paragraph_generation

    try:
        a1, a_status, a_trace, b1, b_status, b_trace = _generate_turn_pair(
            turn_name="turn1",
            topic=topic,
            transcript_text="",
            build_prompt=build_prompt,
            generate_turn=generate_turn,
            api_key=api_key,
            card=card,
        )
        provider_statuses["openai_a"] = a_status
        provider_statuses["openai_b"] = b_status
        trace.extend(a_trace)
        trace.extend(b_trace)
        turns.append({"turn": 1, "a": a1, "b": b1})
        _append(transcript, "A", 1, a1)
        _append(transcript, "B", 1, b1)

        transcript_text = "\n".join(transcript)
        a2, a_status, a_trace, b2, b_status, b_trace = _generate_turn_pair(
            turn_name="turn2",
            topic=topic,
            transcript_text=transcript_text,
            build_prompt=build_prompt,
            generate_turn=generate_turn,
            api_key=api_key,
            card=card,
            opponent_last_a=b1,
            opponent_last_b=a1,
        )
        provider_statuses["openai_a"] = a_status
        provider_statuses["openai_b"] = b_status
        trace.extend(a_trace)
        trace.extend(b_trace)
        turns.append({"turn": 2, "a": a2, "b": b2})
        _append(transcript, "A", 2, a2)
        _append(transcript, "B", 2, b2)

        transcript_text = "\n".join(transcript)
        a3, a_status, a_trace, b3, b_status, b_trace = _generate_turn_pair(
            turn_name="turn3",
            topic=topic,
            transcript_text=transcript_text,
            build_prompt=build_prompt,
            generate_turn=generate_turn,
            api_key=api_key,
            card=card,
            opponent_last_a=b2,
            opponent_last_b=a2,
        )
        provider_statuses["openai_a"] = a_status
        provider_statuses["openai_b"] = b_status
        trace.extend(a_trace)
        trace.extend(b_trace)
        turns.append({"turn": 3, "a": a3, "b": b3})
    except Exception as exc:
        raw_reason = str(exc)
        if raw_reason.startswith("semantic style-anchor invariant failed:"):
            turn_name = raw_reason.split(":", 1)[1]
            return {
                **_blocked_with_trace("style-anchor invariant failed", turn_name, trace, topic),
                "run_id": run_id,
                "provider_statuses": provider_statuses,
            }
        if raw_reason.startswith("semantic paragraph invariant failed:"):
            turn_name = raw_reason.split(":", 1)[1]
            return {
                **_blocked_with_trace("paragraph invariant failed", turn_name, trace, topic),
                "run_id": run_id,
                "provider_statuses": provider_statuses,
            }
        if raw_reason.startswith("semantic slot invariant failed:"):
            turn_name = raw_reason.split(":", 1)[1]
            return {
                **_blocked_with_trace("slot invariant failed", turn_name, trace, topic),
                "run_id": run_id,
                "provider_statuses": provider_statuses,
            }
        return {
            **_blocked_with_trace("symmetric live unavailable", raw_reason, trace, topic),
            "run_id": run_id,
            "provider_statuses": provider_statuses,
        }

    elapsed_seconds = round(time.time() - started_at, 3)
    return {
        "ok": True,
        "mode": "live",
        "run_id": run_id,
        "generation_lane": generation_lane,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "provider_statuses": provider_statuses,
        "elapsed_seconds": elapsed_seconds,
        "debate": {
            "topic": topic,
            "turn_count": 3,
            "participants": {"a": "GPT", "b": "GPT"},
            "turns": turns,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_debate_v4({}), ensure_ascii=False))
