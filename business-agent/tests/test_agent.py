from app.ai.agent import apply_decision, prepare_initial_message
from app.ai.state import DealState
from tests.conftest import FakeLLM


def decision(**over):
    base = {
        "intent": "negotiation", "interest_level": "high", "reply_text": "Хорошо, договорились",
        "send_sticker_mood": "agree",
        "state_update": {
            "conversation_stage": "agreed", "counterparty_role": "seller", "product_type": "NFT",
            "item_description": "Plush Pepe #7", "item_attributes": [{"name": "model", "value": "Pumpkin"}],
            "quantity": 1, "seller_price": "15", "buyer_target_price": None, "agreed_price": "15", "currency": "TON",
            "payment_method": None, "new_objections": [], "new_agreements": ["цена 15 TON"],
        },
        "opt_out": False, "handoff_required": False, "handoff_reason": None, "ready_for_deal": True, "owner_note": None,
    }
    base.update(over)
    return base


def run(dec, transcript, latest=None, allowed=frozenset({"cryptobot"})):
    return apply_decision(dec, DealState(), transcript_texts=transcript, latest_contact_text=latest or transcript[-1],
                          allowed_bot_usernames=set(allowed), deal_created=False, deal_paid=False)


def test_mentioned_price_is_accepted_and_ready():
    r = run(decision(), ["Продаю Plush Pepe за 15 TON"])
    assert r.state.agreed_price == "15" and r.state.currency == "TON"
    assert r.ready_for_deal and r.reply_text and not r.handoff


def test_invented_price_rejected():
    d = decision()
    d["state_update"]["agreed_price"] = "9"
    d["state_update"]["seller_price"] = "9"
    r = run(d, ["Продаю Plush Pepe за 15 TON"])
    assert r.state.agreed_price is None
    assert not r.ready_for_deal
    assert any("agreed_price" in x for x in r.rejected_updates)


def test_invented_currency_rejected():
    d = decision()
    d["state_update"]["currency"] = "USDT"
    r = run(d, ["Продаю за 15 тон"])
    assert r.state.currency is None


def test_foreign_bot_in_contact_message_triggers_handoff():
    r = run(decision(reply_text="Работаю только через нашего бота"), ["Давай через @super_garant_bot за 15 TON"])
    assert r.handoff
    assert "@super_garant_bot" in r.state.suspicious_links
    assert r.sticker_mood == "none"


def test_reply_with_false_claim_not_sent():
    r = run(decision(reply_text="Оплата уже отправлена!"), ["за 15 TON ок"])
    assert r.reply_text is None and r.handoff and r.reply_problems


def test_opt_out_detected_even_if_model_misses_it():
    r = run(decision(opt_out=False, ready_for_deal=False, reply_text=None), ["не пишите мне больше"])
    assert r.opt_out
    assert r.state.conversation_stage == "declined"


async def test_initial_message_falls_back_on_invented_numbers():
    llm = FakeLLM({"text": "Привет, Иван! Куплю ваш подарок за 100 TON", "used_profile_fields": ["name"]})
    text, adapted = await prepare_initial_message(llm, "Здравствуйте! Интересует ваш подарок?", {"name": "Иван"},
                                                  allow_adaptation=True, allowed_bot_usernames=set())
    assert text == "Здравствуйте! Интересует ваш подарок?" and not adapted


async def test_initial_message_adapted_from_profile_only():
    llm = FakeLLM({"text": "Иван, здравствуйте! Интересует ваш подарок PlushPepe-7?", "used_profile_fields": ["name"]})
    text, adapted = await prepare_initial_message(
        llm, "Здравствуйте! Интересует ваш подарок?", {"name": "Иван", "attributes": {"gift": "PlushPepe-7"}},
        allow_adaptation=True, allowed_bot_usernames=set())
    assert adapted and "Иван" in text
