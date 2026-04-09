# ==== _speaker_prompt ====
def _speaker_prompt(
    speaker: str,
    provider: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    transcript: str,
    turn_no: int,
    stage_label: str,
) -> str:
    own_position = cfg.side_a if speaker == "A" else cfg.side_b
    opposing_position = cfg.side_b if speaker == "A" else cfg.side_a
    role_name = f"Fighter {speaker} ({_provider_label(provider)})"
    opponent_last = _opponent_last_statement(speaker, turns)
    proposition_lock_block = _proposition_lock_prompt_block(cfg)
    opening_contract_block = _opening_contract_prompt_block(cfg, speaker, turn_no)
    three_turn_block = _three_turn_prompt_block(cfg, turn_no)
    return (
        f"You are {role_name} in a structured debate prototype.\n"
        f"Topic: {cfg.topic}\n"
        f"Your position: {own_position}\n"
        f"Opponent position: {opposing_position}\n"
        f"Current round: Turn {turn_no} / {cfg.turn_count}\n"
        f"Stage label: {stage_label}\n"
        "Goal: win the exchange by attacking the opponent's latest core and keeping your own line standing.\n"
        "Core failure rule: generic explanation, both-sides language, burden restatement without a concrete hit, or neutral closing counts as failure.\n"
        "Requirements:\n"
        "- Respond entirely in natural Japanese.\n"
        "- Return strict JSON only.\n"
        "- Schema: {\"speech\":\"...\",\"move\":\"opening|rebuttal|rally|finish\",\"meta\":{\"phase\":\"opening|rebuttal|rally\",\"finish_intent\":\"push|finish|extend\",\"end_match\":\"yes|no\",\"opening_contract\":{\"claim_scope\":\"...\",\"comparison_axis\":\"...\",\"acceptance_condition\":\"...\",\"anti_reframe_guard\":\"...\",\"exception_policy\":\"...\",\"burden_target\":\"...\"}}}\n"
        "- meta is hidden scaffold only. Speech must not contain planning, judging, structure labels, or third-person commentary about the debate.\n"
        "- Do not begin or end the speech with labels like はい, いいえ, 結論:, 賛成, or 反対.\n"
        "- Keep at least one topic-specific concrete noun visible in every turn.\n"
        "- Same-claim paraphrase is prohibited. Each turn must react to the opponent's immediate previous claim.\n"
        "- Use only one very short receive line for the opponent's last move. Do not summarize it at length.\n"
        f"{proposition_lock_block}"
        "- Write a dense sequential debate response. In Japanese, target 300 to 800 characters.\n"
        f"{three_turn_block}"
        f"{opening_contract_block}"
        "- Do not use formulas such as 'Turn 1でAは...' or 'Turn 2でBは...'.\n"
        "- Do not quote the opponent at length. If quotation is necessary, use only a very short phrase.\n"
        "- Prefer topic-grounded burdens such as cost, safety, responsibility, implementation, or observed examples over abstract debate scaffolding.\n"
        "- Avoid recurring scaffolds such as 補助線, 本体, 検証指標, 骨組み, 停止条件, 移行コスト, 成り立つライン, 条件を閉じ切る.\n"
        "- If you use an analogy, make it natural and tied to the topic rather than a stock metaphor.\n"
        f"{_mode_prompt_rules(cfg.mode)}"
        "- If there is no opponent statement yet, open by stating your own thesis and two concrete supports.\n"
        "- If opponent logic collapses, attempt to finish the debate.\n"
        "- If you say the opponent collapses, attach one reason.\n"
        "- Set meta.end_match=yes only when you believe the exchange should stop now because of collapse, decisive rebuttal, proposition retreat, or issue loop.\n"
        "- If the opponent changed the proposition, call it out explicitly.\n"
        "- If the opponent shifts burden of proof or breaks its own definition, attack that structure.\n"
        f"{_speaker_role_rules(provider)}"
        "- Do not mention being an AI or the JSON schema.\n"
        f"Opponent last statement:\n{opponent_last}\n"
        f"Transcript so far:\n{transcript or '(none yet)'}\n"
    )


# ==== _three_turn_prompt_block ====
def _three_turn_prompt_block(cfg: DebateConfig, turn_no: int) -> str:
    if cfg.turn_count != 3:
        return ""
    topic = _clean_text(cfg.topic or "")
    dignity_topic = "命" in topic and "値段" in topic and "許され" in topic
    short_payload = _needs_short_stance_boost(cfg, "A") or _needs_short_stance_boost(cfg, "B")
    if turn_no == 1:
        base = (
            "- 3-turn mode.\n"
            "- Turn 1 = claim first: clear stance first, then two topic-specific concrete supports.\n"
            "- Do not begin with evaluation language, proof-criteria language, or opponent reference.\n"
        )
        if short_payload:
            base += "- If your stated position is short, replace it with a topic-grounded claim instead of bare はい/いいえ.\n"
        if dignity_topic:
            base += (
                "- This topic is about pricing human life: ground the opening in insurance, compensation, medical resources, safety regulation, triage, cost-effectiveness, dignity, or public policy.\n"
                "- Do not use generic scaffolding like 補助線, 本体, 検証指標, 骨組み, 停止条件, 移行コスト.\n"
            )
        return base
    if turn_no == 2:
        base = (
            "- Turn 2 = rebuttal.\n"
            "- Include exactly these moves: one short receive of the opponent core, one concrete rebuttal, one push for your side.\n"
            "- Do not spend the turn only re-announcing burden or comparison axis.\n"
        )
        if short_payload:
            base += "- If your stated position is short, the concrete rebuttal must name at least one topic noun, example, market, policy, or operational detail.\n"
        if dignity_topic:
            base += (
                "- Stay inside the topic of pricing human life and use concrete policy or compensation examples instead of generic debate scaffolding.\n"
            )
        return base
    base = (
        "- Turn 3 = closing.\n"
        "- Close the existing battlefield: explain why your side remains, why the opponent fails, and end with one short closing punch.\n"
        "- Do not open a new battlefield or end neutrally.\n"
    )
    if dignity_topic:
        base += (
            "- Closing must still be grounded in life valuation, public policy, compensation, triage, or dignity; avoid generic abstract wrappers.\n"
        )
    return base


# ==== _three_turn_grounded_surface ====
def _three_turn_grounded_surface(
    speaker: str,
    cfg: DebateConfig,
    turn_no: int,
    latest_opponent: str = "",
) -> str:
    proposition_lock = _build_proposition_lock(cfg)
    own_line = _three_turn_resolution_line(cfg.side_a if speaker == "A" else cfg.side_b, speaker, proposition_lock)
    own_line = _clean_text(own_line)
    contract = _build_opening_contract(cfg, cfg.side_a if speaker == "A" else cfg.side_b)
    issue_primary = _three_turn_issue_anchor(cfg, 0)
    issue_secondary = _three_turn_issue_anchor(cfg, 1)
    concrete = _three_turn_concrete_support(speaker, proposition_lock, min(turn_no, 2 if turn_no == 2 else 1 if turn_no == 1 else 2))
    opponent_focus = _select_focus_term(latest_opponent, [issue_primary, issue_secondary]) if latest_opponent else issue_primary
    topic = _clean_text(cfg.topic or "")
    lane = _topic_lane(topic)
    lane_terms = _topic_lane_terms(topic, latest_opponent, own_line)
    lane_term_a = lane_terms[0] if lane_terms else issue_primary
    lane_term_b = lane_terms[1] if len(lane_terms) > 1 else issue_secondary
    short_stance = _needs_short_stance_boost(cfg, speaker)
    short_hook, short_metaphor = _short_stance_topic_hook(cfg)
    if turn_no == 1:
        if speaker == "A":
            if "原発" in topic or "電力" in topic or "再エネ" in topic:
                return _sanitize_fighter_speech(
                    "私は原発維持を支持する。"
                    " 原発は短期の安定供給と低炭素の基幹電源としてまだ価値があり、LNG輸入増と電力価格高騰だけで穴埋めする方が家計と産業の負担は重い。"
                    " さらに安全規制、廃炉積立、賠償枠、最終処分の計画を現実に積み上げれば、維持の根拠はまだ残る。"
                    " 灯りを消す前に、代わりの発電所と金庫を先に用意できるなら維持の理由は残る。"
                    f" だから{own_line}"
                )
            if short_stance:
                return _sanitize_fighter_speech(
                    f"私は{own_line}。"
                    f" {short_hook}を並べると、この命題はまだ前に進める。"
                    f" {short_metaphor}。"
                    f" だから{own_line}"
                )
            return _sanitize_fighter_speech(
                f"私は{own_line}。{concrete} {issue_primary}を見ても、この立場を崩す材料はまだ足りない。だから{own_line}"
            )
        if short_stance:
            return _sanitize_fighter_speech(
                f"{_topic_grounded_short_claim(cfg, speaker)}"
                f" {short_hook}を現実に置くと、この命題は簡単には立たない。"
                f" {short_metaphor}。"
            )
        return _sanitize_fighter_speech(
            f"私は{own_line}。{concrete} この命題を通すにはまだ足りないものがある。"
        )
    if turn_no == 2:
        if speaker == "A":
            if lane == "science":
                return _a_turn2_structured_rebuttal(
                    own_line,
                    opponent_focus,
                    f"{lane_term_a}や{lane_term_b}の観測は局所的な器用さや適応を示しても、火や金属加工や共同作業まで連続して立証していない。",
                    "だからその具体例から一般命題までは伸びず、こちらの立場は崩れない。",
                )
            if lane == "social":
                return _a_turn2_structured_rebuttal(
                    own_line,
                    opponent_focus,
                    f"{lane_term_a}や{lane_term_b}の現場を見ても、制度や運用を左右する具体条件はまだ詰め切れていない。",
                    "だから単発の懸念や例外から全体の制度判断までは飛べず、こちらの主張の方が残る。",
                )
            if lane == "product":
                return _a_turn2_structured_rebuttal(
                    own_line,
                    opponent_focus,
                    f"{lane_term_a}や{lane_term_b}の具体例は一部の機能や運用を示すだけで、採用条件そのものを固定した証拠にはなっていない。",
                    "だから相手の具体例から市場全体の結論へは伸びず、こちらの命題の方が残る。",
                )
            if short_stance:
                return _a_turn2_structured_rebuttal(
                    own_line,
                    opponent_focus,
                    f"{short_hook}まで具体に置くと、相手は一番重い現実条件を崩せていない。",
                    "だからその押し方だけでは命題は倒れず、こちらの立場を維持できる。",
                )
            return _a_turn2_structured_rebuttal(
                own_line,
                opponent_focus,
                _three_turn_concrete_support("A", proposition_lock, 2),
                "だからその具体例だけでは命題は倒れず、こちらの主張を押し返せる。",
            )
        if ("教育" in topic or "初等教育" in topic) and "生成" in topic:
            return _education_limited_rebuttal(cfg, own_line)
        if "原発" in topic or "電力" in topic or "再エネ" in topic:
            return _sanitize_fighter_speech(
                "あなたは実行条件を整えれば維持できると言う。だがその前提は崩れている。"
                " 福島第一の廃炉・賠償は長期の公的負担を残し、六ヶ所再処理や最終処分場もなお未決のままだ。"
                " 事故・廃炉・核廃棄物のコストを最後に誰が引き受けるのかが閉じない限り、便益だけを理由に維持は選べない。"
                " 壊れかけの橋に保険をかけても橋そのものは直らない。"
                f" だから{own_line}"
            )
        if "saas" in topic.lower():
            return _sanitize_fighter_speech(
                "相手の核は、垂直統合とAIでSaaSは再成長できるという点だ。"
                " だがVeevaやProcoreのような勝ち筋は、vertical SaaSの深い業界運用、長い導入期間、重い切替コストに支えられた例外であって、汎用SaaS全体の再成長をそのまま保証しない。"
                " CACは上がり、PLGだけで伸びる領域は狭まり、APIやデータ独自性もSalesforceやServiceNow、クラウド基盤に吸収されれば価格競争へ戻る。"
                f" だから局所的な成功例から市場全体の命題は立たず、{own_line}"
            )
        if short_stance:
            return _sanitize_fighter_speech(
                f"相手の核は{issue_primary}だ。"
                f" だが{_three_turn_concrete_support('B', proposition_lock, 2)}"
                f" {short_hook}だけではまだ命題は立たない。"
                f" {short_metaphor}。"
                f" そこを越えられない限り、{own_line}"
            )
        return _sanitize_fighter_speech(
            f"相手の核は「{opponent_focus}」だ。"
            f" だが{_three_turn_concrete_support('B', proposition_lock, 2)}"
            f" そこが抜けたままでは、{own_line}"
        )
    if speaker == "A":
        if "原発" in topic or "電力" in topic or "再エネ" in topic:
            return _sanitize_fighter_speech(
                "最後に残るのは、事故・廃炉・燃料コストを誰が負担するかを制度で閉じられるかという一点だ。"
                " 相手は負担の存在を言うが、火力依存による電気代高騰、LNG輸入増、CO2の積み増しという別の負担を軽く見ている。"
                " 独立積立、保険プール、発電事業者の厳格負担、送電と代替電源の併設まで含めて条件を法制化できるなら、維持は単なる先送りではない。"
                " 壊れかけた橋なら渡るのをやめるか、補強して通すかの違いであって、村の灯りごと消す話ではない。"
                " 金庫を先に作れるなら、原発維持はまだ合理的だ。"
                f" だから{own_line}"
            )
        if short_stance:
            return _sanitize_fighter_speech(
                f"最後に残るのは{issue_secondary}だ。"
                f" {short_hook}まで並べても相手は決め手を作れていない。"
                f" {short_metaphor}。"
                f" だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"最後に残るのは「{issue_secondary}」だ。{_three_turn_concrete_support('A', proposition_lock, 2)} だから{own_line}"
        )
    if "原発" in topic or "電力" in topic or "再エネ" in topic:
        return _sanitize_fighter_speech(
            "最後まで消えないのは、原発の事故・廃炉・核廃棄物の負担を未来に誰が引き受けるのかという一点だ。"
            " 福島の後始末、最終処分場の未決着、老朽炉の延命コストを見れば、相手は便益を語っても負担の出口を示せていない。"
            " 再エネ・蓄電・送電強化の組み合わせと比べてなお維持が必要だと立証できない限り、原発維持は未来への賭けを続ける話になる。"
            " バケツを増やしても穴の空いたダムは止まらない。"
            f" だから{own_line}"
        )
    if lane == "science":
        return _sanitize_fighter_speech(
            f"相手の核は、{opponent_focus}を積めば{topic or 'この命題'}が立つという点だ。"
            f" しかし{lane_term_a}や{lane_term_b}の観測だけでは、進化経路や物理制約を越えてその一般化は成立しない。"
            f" だから論題としての断定はまだできず、{own_line}"
        )
    if lane == "product":
        return _sanitize_fighter_speech(
            f"相手の核は、{opponent_focus}が残るから{topic or 'この命題'}は立つという点だ。"
            f" しかし{lane_term_a}や{lane_term_b}の具体例は一部の機能や局面を示すだけで、運用統合や採用条件の穴までは埋めていない。"
            f" だから命題全体の優位は固定できず、{own_line}"
        )
    if short_stance:
        return _sanitize_fighter_speech(
            f"最後まで消えないのは{issue_secondary}の負担だ。"
            f" {short_hook}を現実に並べると、相手の立場はまだ足りない。"
            f" {short_metaphor}。"
            f" だから{own_line}"
        )
    return _sanitize_fighter_speech(
        f"最後まで消えないのは「{issue_secondary}」の負担だ。{_three_turn_concrete_support('B', proposition_lock, 2)} だから{own_line}"
    )


# ==== _three_turn_repair_speech ====
def _three_turn_repair_speech(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    latest_opponent: str = "",
) -> str:
    topic = _clean_text(cfg.topic or "")
    if (
        speaker == "B"
        and turn_no == 2
        and _needs_short_stance_boost(cfg, "B")
    ):
        own_line = _clean_text(cfg.side_b or "その立場は立たない。")
        opponent_line = _clean_text(latest_opponent or "")
        topic_terms = _extract_focus_terms(topic)
        opponent_terms = [term for term in _extract_focus_terms(opponent_line) if term not in JP_STOPWORDS]
        own_terms = [term for term in _extract_focus_terms(own_line) if term not in JP_STOPWORDS]
        concrete_terms: list[str] = []
        for term in opponent_terms + topic_terms + own_terms:
            if len(term) < 2:
                continue
            if term in concrete_terms:
                continue
            concrete_terms.append(term)
            if len(concrete_terms) >= 4:
                break
        concrete_a = concrete_terms[0] if concrete_terms else (topic_terms[0] if topic_terms else "具体例")
        concrete_b = concrete_terms[1] if len(concrete_terms) > 1 else (topic_terms[1] if len(topic_terms) > 1 else own_terms[0] if own_terms else "現場")
        if "金" in topic and "銀" in topic:
            return _sanitize_fighter_speech(
                "相手の核は、銀の方が長期保有で有利だという点だ。"
                " だが中央銀行の準備資産運用では、LBMA水準の流動性、COMEXを含む市場の厚み、保管と担保の実務がまず問われる。"
                " 銀は太陽光や電子部品の需要で価格が振れやすく、決済と担保で使う資産としては金ほど安定しない。"
                " だから長期保有の優位は固定できず、金より銀の方が長期保有に向いているとは言えない。"
            )
        opponent_core = opponent_line.split("。")[0].strip() if opponent_line else ""
        if opponent_core:
            opening = f"相手の核は、{opponent_core}という点だ。"
        else:
            opening = "相手の核は、その前提を一般化して押し切れるという点だ。"
        support = (
            f" だが{concrete_a}や{concrete_b}のような具体例では、"
            f"{concrete_a}の条件と{concrete_b}の条件がずれれば同じ結論はそのまま通らない。"
        )
        causal = f" だから相手の前提は一般化できず、この論点だけでは断定は成立しない。"
        closing = f" したがって、{own_line}"
        return _sanitize_fighter_speech(opening + support + causal + closing)
    return _three_turn_grounded_surface(speaker, cfg, turn_no, latest_opponent)


# ==== _sanitize_fighter_speech ====
def _sanitize_fighter_speech(text: str) -> str:
    cleaned = _naturalize_surface_text(text)
    cleaned = _strip_stance_meta_leakage(cleaned)
    label_prefix = r"(?:受け取りました|受け取り|受け|相手主張|相手|反論|押し|締め|最後の一撃)"
    label_repairs = [
        (r"^受け取りました[:：]\s*", ""),
        (r"^受け取る[:：]\s*", ""),
        (r"^受け取る[。.]\s*", ""),
        (r"^受け[:：]\s*", ""),
        (r'^受け取りました[:：]\s*([「『"].*)$', r"\1"),
        (rf"^(?:{label_prefix})(?:[:：]|[。.]|\s)+(?:なし[。.]?\s*)?", ""),
        (r"^次の一手(?:は|として)?[:：]?\s*([^。！？!?]+)[。！？!?]\s*", ""),
        (r"^見たい筋(?:は|として)?[:：]?\s*([^。！？!?]+)[。！？!?]\s*", ""),
        (r"^評価モード[:：]?\s*([^。！？!?]+)[。！？!?]\s*", ""),
        (r"^討論として[:：]?\s*([^。！？!?]+)[。！？!?]\s*", ""),
        (r"^相手[:：]\s*([^。！？!?]+?)(?:と主張|と言う|としている)\s*", r"相手は\1と主張している。 "),
    ]
    for pattern, replacement in label_repairs:
        while True:
            updated = re.sub(pattern, replacement, cleaned)
            if updated == cleaned:
                break
            cleaned = updated
    replacements = {
        "ここで": "",
        "盤面": "話",
        "構造": "中身",
        "戦略": "主張",
        "分析": "話",
        "勝ち筋": "話",
        "成り立つライン": "立場の条件",
        "閉じ切れていない": "まだ処理されていない",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("次の一手として", "")
    cleaned = cleaned.replace("この返しで", "")
    cleaned = cleaned.replace("このラリーは", "")
    cleaned = cleaned.replace("押し:", "")
    cleaned = cleaned.replace("押し：", "")
    cleaned = cleaned.replace("最後の一撃:", "")
    cleaned = cleaned.replace("最後の一撃：", "")
    cleaned = cleaned.replace("元の立場を使うと", "")
    cleaned = cleaned.replace("検証指標を入れる", "指標を見る")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _strip_stance_meta_leakage(cleaned)
    cleaned = _repair_incomplete_sentence_ending(cleaned)
    return _naturalize_surface_text(cleaned)


# ==== _three_turn_validation_report ====
def _three_turn_validation_report(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    speech: str,
    latest_opponent: str = "",
) -> dict[str, Any]:
    debug = _three_turn_density_debug(speech, turn_no, latest_opponent)
    grounding = _topic_grounding_report(cfg, speech)
    topic = _clean_text(cfg.topic or "")
    sora_video_topic = (
        "sora" in topic.lower()
        and "動画サービス" in topic
        and ("手を出すべきでなかった" in topic or "手を出すべきだった" in topic)
    )
    failures: list[str] = []
    cleaned = _clean_text(speech)
    char_min = 140 if turn_no in {1, 2} else 100
    sentence_min = 3
    if debug["sentence_count"] < sentence_min:
        failures.append("too few sentences")
    if debug["char_count"] < char_min:
        failures.append("too short")
    if not _has_self_stance_reference(cfg, speaker, speech):
        failures.append("missing self stance")
    if _contains_banned_surface_meta(speech) or _looks_like_design_memo_speech(speech):
        failures.append("contains surface meta")
    if grounding["grounded_keyword_count"] and grounding["grounded_keyword_count"] < 3:
        failures.append("insufficient topic grounding")
    if grounding["banned_template_phrase_count"]:
        failures.append("contains banned template phrasing")
    if grounding["bare_stance_tokens"]:
        failures.append("contains bare stance token")
    if re.search(r"(だからはい|だからいいえ|(^|[。！？!?\\s])はい|(^|[。！？!?\\s])いいえ)\\s*$", cleaned):
        failures.append("ends with bare stance suffix")
    if turn_no == 1:
        if not debug["has_concrete_support"]:
            failures.append("opening lacks concrete support")
        if not _has_acceptance_condition_signal(speech):
            failures.append("opening lacks acceptance condition")
        if _looks_like_skeleton_three_turn_opening(speech):
            failures.append("skeleton opening")
        if sora_video_topic and grounding["grounded_keyword_count"] < 4:
            failures.append("opening lacks topic-grounded opening")
        if sora_video_topic:
            cleaned = _clean_text(speech)
            if cleaned.startswith(("だからはい", "だからいいえ", "先に押さえたい", "周辺条件ばかり")):
                failures.append("opening starts with banned generic scaffold")
            if not any(token in cleaned for token in ["SORA", "撤退", "動画サービス", "OpenAI", "GPT"]):
                failures.append("opening missing case anchor")
    elif turn_no == 2:
        if not debug["has_counter_to_opponent"]:
            failures.append("rebuttal missing direct counter")
        if not debug["has_concrete_support"]:
            failures.append("rebuttal lacks concrete support")
        if not any(token in _clean_text(speech) for token in ["それでも", "だから", "残る", "本題", "結局"]):
            failures.append("rebuttal missing self restate")
        prior_same_side = ""
        if turns:
            latest_turn = turns[-1] if turns else {}
            prior_same_side = _clean_text(latest_turn.get("a" if speaker == "A" else "b") or "")
        if latest_opponent and not _has_opponent_reference_in_first_sentence(speech, latest_opponent):
            failures.append("rebuttal first sentence missing opponent reference")
        if prior_same_side:
            if _first_sentence(speech) == _first_sentence(prior_same_side):
                failures.append("rebuttal repeats prior first sentence")
            if _final_sentence(speech) == _final_sentence(prior_same_side):
                failures.append("rebuttal repeats prior last sentence")
            if _has_long_overlap(speech, prior_same_side, 20):
                failures.append("rebuttal reuses long prior span")
    else:
        if not _has_closing_punch_signal(speech):
            failures.append("closing lacks punch")
        if not debug["has_counter_to_opponent"]:
            failures.append("closing missing opponent collapse")
        if not any(token in _clean_text(speech) for token in ["残る", "立たない", "届いていない", "崩れている", "消えない", "断定はできない", "とは限らない"]):
            failures.append("closing missing self-win reason")
    debug["three_turn_contract_pass"] = debug["turn_role_complete"] and not failures
    debug["three_turn_failures"] = failures
    debug["three_turn_speaker"] = speaker
    debug["three_turn_mode"] = cfg.turn_count == 3
    debug.update(grounding)
    return debug


# ==== _three_turn_retry_prompt ====
def _three_turn_retry_prompt(prompt: str, failures: list[str], turn_no: int) -> str:
    if not failures:
        return prompt
    failure_text = ", ".join(failures)
    return (
        f"{prompt}\n"
        "Rewrite because the previous draft failed the 3-turn speaking contract.\n"
        f"Missing requirements: {failure_text}.\n"
        f"For Turn {turn_no}, produce a denser answer with concrete support, direct engagement, and a complete role.\n"
        "Use at least 3 sentences.\n"
        "Include one concrete noun, case, or evidentiary hook.\n"
        "Do not shorten. Do not output a skeleton. Do not stop at axis restatement.\n"
        "Avoid generic debate scaffolding such as 補助線, 本体, 検証指標, 骨組み, 停止条件, 移行コスト.\n"
        "Stay grounded in the actual topic rather than generic yes/no framing.\n"
        "Keep natural Japanese and return strict JSON only.\n"
    )


# FREEZE: current repair lane entrypoint. Keep narrow and repair-only; do not expand it
# back into a general live generation surface.
