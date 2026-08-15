import pytest

from app.chat import parse_commands
from app.chat_store import clear_memory_chats, load_chat_history, save_chat_turn


CTX = {
    "disease": "Atopic dermatitis",
    "dossier": {"gene": "IL4R", "verdict": "Driver"},
    "session": [{"gene": "IL4R"}, {"gene": "FLG"}, {"gene": "S100A8"}],
}


def test_search_uses_gene_and_disease():
    cmds = parse_commands("/search", CTX)
    assert cmds[0]["type"] == "search"
    assert cmds[0]["gene"] == "IL4R"
    assert cmds[0]["disease"] == "Atopic dermatitis"


def test_search_named_session_gene():
    cmds = parse_commands("search papers for FLG", CTX)
    assert cmds[0]["gene"] == "FLG"


def test_research_does_not_trigger_search():
    cmds = parse_commands("what does the research say about this verdict?", CTX)
    assert not any(c["type"] == "search" for c in cmds)


def test_action_from_command_is_confirmable():
    from app.chat import _action_from_command, _NEEDS_CONFIRM
    action = _action_from_command({"type": "search", "gene": "IL4R", "disease": "Atopic dermatitis"}, CTX)
    assert action.type in _NEEDS_CONFIRM
    assert "Europe PMC" in action.label


def test_run_another_analysis_is_a_rerun():
    cmds = parse_commands("run another analysis", CTX)
    assert cmds[0]["type"] == "rerun"
    assert cmds[0]["disease"] == "Atopic dermatitis"
    assert cmds[0]["genes"] == ["IL4R", "FLG", "S100A8"]
    assert parse_commands("I disagree, argue this", CTX)[0]["type"] == "argue"
    assert parse_commands("focus FLG", CTX)[0] == {"type": "focus_gene", "gene": "FLG"}


def test_rerun_shows_close_disease_and_gene_change():
    cmd = parse_commands("can you rerun a close disease and the gene for me", CTX)
    assert cmd[0]["type"] == "rerun"
    assert cmd[0]["disease"] == "Psoriasis"
    assert cmd[0]["genes"] == ["IL4R"]


def test_rerun_named_disease_and_genes():
    cmd = parse_commands("rerun psoriasis with FLG and S100A8", CTX)[0]
    assert cmd["type"] == "rerun"
    assert cmd["disease"] == "Psoriasis"
    assert cmd["genes"] == ["FLG", "S100A8"]


def test_rerun_only_named_gene_keeps_same_disease():
    cmd = parse_commands("run again the analysis only for S100A8 same disease", CTX)[0]
    assert cmd["type"] == "rerun"
    assert cmd["disease"] == "Atopic dermatitis"
    assert cmd["genes"] == ["S100A8"]


def test_rerun_named_gene_is_case_insensitive():
    cmd = parse_commands("rerun just s100a8", CTX)[0]
    assert cmd["genes"] == ["S100A8"]
    assert cmd["disease"] == "Atopic dermatitis"


def test_offline_reply_for_narrow_rerun_names_drop_and_skips_panel():
    from app.chat import STYLE_VARIANTS, _action_from_command, _offline_reply

    action = _action_from_command(
        {"type": "rerun", "disease": "Atopic dermatitis", "genes": ["S100A8"]},
        CTX,
    )
    reply = _offline_reply(CTX, [action], [], [], STYLE_VARIANTS[0])
    assert "S100A8" in reply
    assert "Dropping" in reply
    assert "IL4R" in reply
    assert "panel" not in reply.lower()
    assert "session candidates" not in reply.lower()
    assert "queued" not in reply.lower()
    assert not reply.lower().startswith("reading the run")


def test_natural_close_and_change_disease():
    cmd = parse_commands("can you just do a different one which is close to it? change the dieases as well", CTX)[0]
    assert cmd["type"] == "rerun"
    assert cmd["disease"] == "Psoriasis"
    assert cmd["genes"] == ["TYK2"]


def test_make_it_five_genes_keeps_disease_and_closest_neighbours():
    cmd = parse_commands("make it 5 genes", CTX)[0]
    assert cmd["type"] == "rerun"
    assert cmd["disease"] == "Atopic dermatitis"
    assert cmd["genes"][0] == "IL4R"
    assert len(cmd["genes"]) == 5
    assert "IL13" in cmd["genes"]
    assert cmd["reason"].startswith("panel:closest 5 to IL4R")


def test_same_disease_close_pair_picks_il13_with_evidence_pack():
    cmd = parse_commands("let's try a close pair with the same disease", CTX)[0]
    assert cmd["genes"] == ["IL13"]
    assert "pathway neighbour of IL4R" in cmd["reason"]


def test_remove_genes_and_swap_s100a8():
    cmd = parse_commands("remove il4r and flg and instead of s100a8 try another one", CTX)[0]
    assert cmd["type"] == "rerun"
    assert cmd["disease"] == "Atopic dermatitis"
    assert "IL4R" not in cmd["genes"]
    assert "FLG" not in cmd["genes"]
    assert "S100A8" not in cmd["genes"]
    assert "S100A9" in cmd["genes"]


def test_strip_vocative_drops_email_blob_greeting():
    from app.chat import _strip_vocative
    assert _strip_vocative("Elyasirankhah — your last analysis was seeded.").startswith("your last")
    assert _strip_vocative("Hey Elyas, the verdict stands.").startswith("the verdict")
    cmd = parse_commands("let's try a close pair with the same disease", CTX)[0]
    assert cmd["type"] == "rerun"
    assert cmd["disease"] == "Atopic dermatitis"
    assert cmd["genes"] and cmd["genes"][0] not in {"IL4R", "FLG", "S100A8"}
    assert cmd["reason"].startswith("close_pair:")


def test_close_pair_avoids_prior_pairs():
    prior_ctx = dict(CTX)
    prior_ctx["prior_pairs"] = [
        {"disease": "Atopic dermatitis", "gene": "IL13"},
        {"disease": "Atopic dermatitis", "gene": "IL13RA1"},
    ]
    cmd = parse_commands("give me a sibling gene for the same disease", prior_ctx)[0]
    assert cmd["genes"][0] not in {"IL4R", "FLG", "S100A8", "IL13", "IL13RA1"}
    assert cmd["genes"][0] == "JAK1"


def test_close_pair_action_label_carries_pathway_note():
    from app.chat import _action_from_command

    action = _action_from_command(
        {"type": "rerun", "disease": "Atopic dermatitis", "genes": ["IL13"], "reason": "close_pair:pathway neighbour of IL4R"},
        CTX,
    )
    assert action.type == "rerun"
    assert "close pair" in action.label
    assert action.reason and action.reason.startswith("close_pair")


def test_style_variants_rotate_across_turns():
    from app.chat import ChatRequest, ChatMessage, _pick_style, STYLE_VARIANTS

    def style_for(turn: int, user_text: str) -> str:
        req = ChatRequest(
            run_id="run-x",
            messages=(
                [ChatMessage(role="user", content="hi"), ChatMessage(role="assistant", content="prev")] * turn
                + [ChatMessage(role="user", content=user_text)]
            ),
            context={},
        )
        return _pick_style(req, user_text)

    picks = {style_for(t, f"prompt {t}") for t in range(6)}
    assert len(picks) >= 3
    assert picks.issubset(set(STYLE_VARIANTS))


def test_offline_reply_names_close_pair_and_varies_by_style():
    from app.chat import ClaraAction, STYLE_VARIANTS, _offline_reply

    pending = [
        ClaraAction(
            type="rerun",
            label="Re-run BioLead for Atopic dermatitis · IL13  (close pair · pathway neighbour of IL4R)",
            disease="Atopic dermatitis",
            genes=["IL13"],
            reason="close_pair:pathway neighbour of IL4R",
        )
    ]
    reply_a = _offline_reply(CTX, pending, [], [], STYLE_VARIANTS[0])
    reply_b = _offline_reply(CTX, pending, [], [], STYLE_VARIANTS[2])
    assert "IL13" in reply_a and "IL13" in reply_b
    assert "pathway neighbour of IL4R" in reply_a
    assert "Live" in reply_a
    assert reply_a != reply_b


def test_offline_reply_when_no_pending_varies_and_is_grounded():
    from app.chat import STYLE_VARIANTS, _offline_reply

    a = _offline_reply(CTX, [], [], [], STYLE_VARIANTS[0])
    b = _offline_reply(CTX, [], [], [], STYLE_VARIANTS[2])
    assert a != b
    assert "IL4R" in a or "Atopic dermatitis" in a


def test_challenge_and_defend_options():
    assert parse_commands("challenge this verdict", CTX)[0]["type"] == "argue"
    assert parse_commands("defend this verdict", CTX)[0]["type"] == "defend"
    assert parse_commands("argue for IL4R", CTX)[0]["type"] == "defend"


def test_filter_novel_hits_skips_dossier_papers():
    from app.chat import SearchHit, _ensure_hits_in_reply, _filter_novel_hits

    ctx = {
        "dossier": {
            "gene": "IL4R",
            "evidence": [
                {
                    "title": "Target-engaging therapy improves clinical disease",
                    "citation": "PMID: 27690741",
                    "source_url": "https://pubmed.ncbi.nlm.nih.gov/27690741/",
                }
            ],
        }
    }
    hits = [
        SearchHit(
            title="Target-engaging therapy improves clinical disease",
            url="https://europepmc.org/article/MED/27690741",
            citation="MED:27690741",
        ),
        SearchHit(
            title="A newer IL4R paper",
            url="https://europepmc.org/article/MED/99999999",
            citation="MED:99999999",
        ),
    ]
    novel = _filter_novel_hits(hits, ctx)
    assert [hit.citation for hit in novel] == ["MED:99999999"]
    reply = _ensure_hits_in_reply("Here is my take on the verdict.", novel)
    assert "A newer IL4R paper" in reply
    assert "MED:99999999" in reply
    assert "Here is my take" in reply


@pytest.mark.asyncio
async def test_signed_user_chat_history_memory_fallback(monkeypatch):
    monkeypatch.setattr("app.chat_store.get_db", lambda: None)
    clear_memory_chats()
    persisted = await save_chat_turn(
        user_id="user-1",
        user_email="scientist@example.com",
        run_id="run-1",
        disease="Atopic dermatitis",
        messages=[
            {"role": "user", "content": "I disagree with the verdict."},
            {"role": "assistant", "content": "Let's inspect the evidence."},
        ],
    )
    messages, durable = await load_chat_history(user_id="user-1", run_id="run-1")
    assert persisted is False
    assert durable is False
    assert [row["role"] for row in messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_command_cards_are_persisted_in_memory(monkeypatch):
    monkeypatch.setattr("app.chat_store.get_db", lambda: None)
    clear_memory_chats()
    await save_chat_turn(
        user_id="user-1",
        user_email="scientist@example.com",
        run_id="run-2",
        disease="Atopic dermatitis",
        messages=[
            {"role": "user", "content": "run another analysis"},
            {"role": "assistant", "content": "Confirm the command under this message."},
            {
                "role": "command",
                "content": "Re-run BioLead for Atopic dermatitis · IL4R, FLG, S100A8",
                "command": {
                    "status": "pending",
                    "label": "Re-run BioLead for Atopic dermatitis · IL4R, FLG, S100A8",
                    "action": {"type": "rerun", "label": "Re-run", "disease": "Atopic dermatitis"},
                },
            },
        ],
    )
    messages, _durable = await load_chat_history(user_id="user-1", run_id="run-2")
    assert [row["role"] for row in messages] == ["user", "assistant", "command"]
    assert messages[2]["command"]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_and_delete_chat_sessions(monkeypatch):
    monkeypatch.setattr("app.chat_store.get_db", lambda: None)
    from app.chat_store import delete_chat_session, list_chat_sessions

    clear_memory_chats()
    await save_chat_turn(
        user_id="user-1",
        user_email="scientist@example.com",
        run_id="run-a",
        chat_id="chat-a",
        disease="Atopic dermatitis",
        messages=[{"role": "user", "content": "run another analysis"}],
    )
    await save_chat_turn(
        user_id="user-1",
        user_email="scientist@example.com",
        run_id="run-b",
        chat_id="chat-b",
        disease="Psoriasis",
        messages=[{"role": "user", "content": "challenge this verdict"}],
    )
    sessions, durable = await list_chat_sessions(user_id="user-1")
    assert durable is False
    by_id = {row["chat_id"]: row for row in sessions}
    assert set(by_id) == {"chat-a", "chat-b"}
    assert by_id["chat-a"]["title"] == "run another analysis"
    assert await delete_chat_session(user_id="user-1", chat_id="chat-a") is True
    remaining, _ = await list_chat_sessions(user_id="user-1")
    assert [row["chat_id"] for row in remaining] == ["chat-b"]


def test_first_name_prefers_given_name_not_email_blob():
    from app.chat import _first_name, _verified_context

    assert _first_name("Elyas Irankhah") == "Elyas"
    assert _first_name("Irankhah, Elyas") == "Elyas"
    assert _first_name("ElyasIrankhah") == "Elyas"
    assert _first_name("elyas.irankhah@example.com") == "Elyas"
    assert _first_name("elyasirankhah@example.com") == ""

    ctx = _verified_context(
        {"scientist": {"name": "Elyas Irankhah", "given_name": "Elyas"}},
        user_id="u1",
        user_email="elyasirankhah@example.com",
    )
    assert ctx["scientist"]["name"] == "Elyas"


def test_offline_reply_after_rerun_does_not_use_full_name():
    from app.chat import ClaraAction, STYLE_VARIANTS, _offline_reply

    ctx = {
        **CTX,
        "scientist": {"name": "Elyas", "signed_in": True},
    }
    action = ClaraAction(
        type="rerun",
        label="Re-run BioLead for Atopic dermatitis · IL13",
        disease="Atopic dermatitis",
        genes=["IL13"],
        reason="close_pair:pathway neighbour of IL4R",
    )
    reply = _offline_reply(ctx, [], [action], [], STYLE_VARIANTS[0])
    assert "IL13" in reply
    assert "Elyasirankhah" not in reply
    assert "Watch the workbench" in reply
    assert "Live" in reply
    assert "Demo" not in reply
    assert "Elyasirankhah" not in reply
    assert "panel" not in reply.lower()
    assert "every candidate" not in reply.lower()


def test_verdict_pushback_explains_insufficient_without_name_or_panel():
    from app.chat import STYLE_VARIANTS, _offline_reply, _strip_vocative

    ctx = {
        "disease": "Atopic dermatitis",
        "dossier": {
            "gene": "IL4",
            "verdict": "Insufficient evidence",
            "executive_summary": "Live retrieve did not converge on causal rescue for IL4.",
            "passenger_case": ["No IL4-selective medicine in atopic dermatitis."],
            "scorecard": {
                "causality": {"value": 18},
                "actionability": {"value": 12},
                "evidence_quality": {"value": 41},
                "independent_pillars": 1,
                "evidence_count": 2,
            },
        },
        "session": [{"gene": "IL4", "verdict": "Insufficient evidence"}],
    }
    user = "why it's insufficinet, i can not accept it"
    assert parse_commands(user, ctx)[0]["type"] == "argue"
    reply = _offline_reply(ctx, [], [], [], STYLE_VARIANTS[0], last_user=user)
    assert "IL4" in reply
    assert "abstain" in reply.lower() or "Insufficient" in reply or "pillars" in reply.lower()
    assert "Elyasirankhah" not in reply
    assert "panel" not in reply.lower()
    assert "tell me what you think about the verdicts" not in reply.lower()
    cleaned = _strip_vocative("Elyasirankhah — I can add IL13 and run the panel.")
    assert not cleaned.lower().startswith("elyas")
    assert "Elyasirankhah" not in cleaned


def test_citation_ask_lists_dossier_sources():
    from app.chat import STYLE_VARIANTS, _offline_reply

    ctx = {
        "disease": "Atopic dermatitis",
        "dossier": {
            "gene": "IL13",
            "verdict": "Driver",
            "evidence": [
                {
                    "title": "Open Targets clinical pharmacology for IL13",
                    "citation": "PMID: 33890792",
                    "source_name": "Open Targets",
                },
                {
                    "title": "Open Targets GWAS credible-set genetics for IL13",
                    "source_name": "Open Targets",
                },
            ],
        },
    }
    user = "can you give me some citation of this process?"
    reply = _offline_reply(ctx, [], [], [], STYLE_VARIANTS[0], last_user=user)
    assert "IL13" in reply
    assert "PMID: 33890792" in reply
    assert "Open Targets GWAS" in reply
    assert "tell me what you think about the verdicts" not in reply.lower()
    assert "Elyasirankhah" not in reply
    assert reply.lower().count("elyas") <= 1
    assert "you asked" not in reply.lower()
    assert not reply.lower().startswith("the strongest anchor")
    assert "queued" not in reply.lower()


_ROBOT_PHRASES = (
    "queued atopic",
    "queued a europe pmc",
    "reading the run with you",
    "the strongest anchor in your dossier is",
    "playing devil's advocate for a moment",
    "mechanistically, queued",
    "you asked “",
    "you asked \"",
    "tell me what you think about the verdicts",
    "elyasirankhah",
    "in the panel",
    "confirm in the panel",
    "pending actions",
)


def _assert_human_voice(reply: str) -> None:
    lower = reply.lower()
    for phrase in _ROBOT_PHRASES:
        assert phrase not in lower, f"robot phrase in Clara reply: {phrase!r}\n{reply}"
    assert reply[0].isupper(), reply
    assert "×" in reply or "x" in lower or any(g in reply for g in ("IL4R", "IL13", "FLG", "S100A8", "JAK1"))


@pytest.mark.asyncio
async def test_make_it_five_genes_via_chat_completion():
    from app.chat import ChatMessage, ChatRequest, chat_completion

    res = await chat_completion(
        ChatRequest(
            run_id="five-genes",
            messages=[ChatMessage(role="user", content="make it 5 genes")],
            context=CTX,
        )
    )
    assert res.pending
    genes = res.pending[0].genes
    assert res.pending[0].disease == "Atopic dermatitis"
    assert genes[0] == "IL4R"
    assert len(genes) == 5
    assert "IL13" in genes
    assert "5" in res.reply or "closest" in res.reply.lower()
    assert "Live" in res.reply
    assert "IL4R" in res.reply


@pytest.mark.asyncio
async def test_clara_language_via_chat_completion():
    from app.chat import ChatMessage, ChatRequest, ClaraAction, chat_completion

    ctx = {
        "disease": "Atopic dermatitis",
        "mode": "demo",
        "scientist": {"name": "Elyas", "given_name": "Elyas"},
        "dossier": {
            "gene": "IL4R",
            "verdict": "Driver",
            "confidence": 88,
            "executive_summary": "IL4R has convergent genetics and dupilumab-class clinical rescue in atopic dermatitis.",
            "scorecard": {
                "causality": {"value": 72},
                "actionability": {"value": 81},
                "evidence_quality": {"value": 84},
                "independent_pillars": 4,
                "evidence_count": 6,
            },
            "evidence": [
                {"title": "Target-engaging therapy improves clinical disease", "citation": "PMID: 27690741"},
                {"title": "Skin eQTL colocalizes with AD GWAS at IL4R", "citation": "Open Targets Genetics"},
            ],
        },
        "session": [
            {"gene": "IL4R", "verdict": "Driver"},
            {"gene": "FLG", "verdict": "Insufficient evidence"},
            {"gene": "S100A8", "verdict": "Passenger"},
        ],
    }
    flg = {
        **ctx,
        "dossier": {
            "gene": "FLG",
            "verdict": "Insufficient evidence",
            "executive_summary": "FLG has human genetic support without a tractable clinical rescue in this run.",
            "passenger_case": ["Loss-of-function genetics is real; actionability is not."],
            "scorecard": {
                "causality": {"value": 34},
                "actionability": {"value": 18},
                "evidence_quality": {"value": 62},
                "independent_pillars": 1,
                "evidence_count": 3,
            },
            "evidence": [
                {"title": "FLG loss-of-function alleles raise AD risk", "citation": "PMID: 16550169"},
            ],
        },
    }

    close = await chat_completion(
        ChatRequest(
            run_id="lang-1",
            messages=[ChatMessage(role="user", content="let's try a close pair with the same disease — IL13")],
            context=ctx,
        ),
        user_email="elyasirankhah@example.com",
    )
    _assert_human_voice(close.reply)
    assert "IL13" in close.reply
    assert "pathway neighbour" in close.reply
    assert "Live" in close.reply
    assert "Dropping" in close.reply
    assert close.pending and close.pending[0].genes == ["IL13"]
    assert close.reply.lower().startswith("queued") is False

    confirmed = await chat_completion(
        ChatRequest(
            run_id="lang-1",
            messages=[
                ChatMessage(role="user", content="let's try a close pair with the same disease — IL13"),
                ChatMessage(role="assistant", content=close.reply),
            ],
            context=ctx,
            confirm=[
                ClaraAction(
                    type="rerun",
                    label="Re-run BioLead for Atopic dermatitis · IL13",
                    disease="Atopic dermatitis",
                    genes=["IL13"],
                    reason="close_pair:pathway neighbour of IL4R",
                )
            ],
        ),
        user_email="elyasirankhah@example.com",
    )
    _assert_human_voice(confirmed.reply)
    assert "Watch the workbench" in confirmed.reply
    assert "Live" in confirmed.reply
    assert "IL13" in confirmed.reply
    assert "— confirmed" not in confirmed.reply.lower()

    cites = await chat_completion(
        ChatRequest(
            run_id="lang-2",
            messages=[ChatMessage(role="user", content="can you give me some citation of this process?")],
            context=ctx,
        ),
        user_email="elyasirankhah@example.com",
    )
    _assert_human_voice(cites.reply)
    assert "PMID: 27690741" in cites.reply
    assert "Skin eQTL" in cites.reply

    push = await chat_completion(
        ChatRequest(
            run_id="lang-3",
            messages=[ChatMessage(role="user", content="why it's insufficient, i can not accept it")],
            context=flg,
        ),
        user_email="elyasirankhah@example.com",
    )
    _assert_human_voice(push.reply)
    assert "FLG" in push.reply
    assert "abstain" in push.reply.lower() or "Insufficient" in push.reply

    score = await chat_completion(
        ChatRequest(
            run_id="lang-4",
            messages=[ChatMessage(role="user", content="what does causality 72 actually mean here?")],
            context=ctx,
        ),
        user_email="elyasirankhah@example.com",
    )
    _assert_human_voice(score.reply)
    assert "72" in score.reply or "causal" in score.reply.lower()
    assert "you asked" not in score.reply.lower()
