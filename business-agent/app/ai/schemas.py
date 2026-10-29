"""JSON-схемы structured outputs."""
from typing import Any


def _nullable(t: str, **extra: Any) -> dict[str, Any]:
    return {"type": [t, "null"], **extra}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_ATTRS = {"type": "array", "items": _obj({"name": {"type": "string"}, "value": {"type": "string"}})}

STICKER_MOODS = ["none", "greeting", "thanks", "agree", "thinking", "deal_done"]
STAGES = ["new", "greeting", "discovery", "negotiation", "agreed", "deal_pending", "closed", "declined"]

DIALOGUE_DECISION_SCHEMA = _obj(
    {
        "intent": {
            "type": "string",
            "enum": [
                "greeting", "question", "interest", "negotiation", "objection", "agreement",
                "not_interested", "opt_out", "media", "off_topic", "unclear", "other",
            ],
        },
        "interest_level": {"type": "string", "enum": ["none", "low", "medium", "high", "unknown"]},
        "reply_text": _nullable("string"),
        "send_sticker_mood": {"type": "string", "enum": STICKER_MOODS},
        "state_update": _obj(
            {
                "conversation_stage": {"anyOf": [{"type": "string", "enum": STAGES}, {"type": "null"}]},
                "counterparty_role": {"anyOf": [{"type": "string", "enum": ["seller", "buyer"]}, {"type": "null"}]},
                "product_type": _nullable("string"),
                "item_description": _nullable("string"),
                "item_attributes": _ATTRS,
                "quantity": _nullable("integer"),
                "seller_price": _nullable("string"),
                "buyer_target_price": _nullable("string"),
                "agreed_price": _nullable("string"),
                "currency": _nullable("string"),
                "payment_method": _nullable("string"),
                "new_objections": {"type": "array", "items": {"type": "string"}},
                "new_agreements": {"type": "array", "items": {"type": "string"}},
            }
        ),
        "opt_out": {"type": "boolean"},
        "handoff_required": {"type": "boolean"},
        "handoff_reason": _nullable("string"),
        "ready_for_deal": {"type": "boolean"},
        "owner_note": _nullable("string"),
    }
)

INITIAL_MESSAGE_SCHEMA = _obj(
    {
        "text": {"type": "string"},
        "used_profile_fields": {"type": "array", "items": {"type": "string"}},
    }
)

MEDIA_ANALYSIS_SCHEMA = _obj(
    {
        "summary": {"type": "string"},
        "objects": {"type": "array", "items": {"type": "string"}},
        "visible_text": _nullable("string"),
        "item_attributes": _ATTRS,
        "events": {"type": "array", "items": {"type": "string"}},
        "tone": _nullable("string"),
        "matches_discussed_item": {"type": "string", "enum": ["yes", "no", "unclear", "not_applicable"]},
        "match_explanation": _nullable("string"),
        "reference_matches": {
            "type": "array",
            "items": _obj(
                {
                    "reference_id": {"type": "integer"},
                    "similarity": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                    "note": {"type": "string"},
                }
            ),
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    }
)

INSTRUCTION_ANALYSIS_SCHEMA = _obj(
    {
        "instruction_type": {
            "type": "string",
            "enum": ["style", "negotiation", "trading", "general", "examples", "mixed", "unclear"],
        },
        "summary": {"type": "string"},
        "new_rules": {"type": "array", "items": {"type": "string"}},
        "removed_rules": {"type": "array", "items": {"type": "string"}},
        "conflicts": {
            "type": "array",
            "items": _obj({"existing": {"type": "string"}, "new": {"type": "string"}, "explanation": {"type": "string"}}),
        },
        "safety_concerns": {"type": "array", "items": {"type": "string"}},
        "proposed": _obj(
            {
                "instructions": {"type": "string"},
                "style": {"type": "string"},
                "negotiation_rules": {"type": "string"},
                "trading_rules": {"type": "string"},
                "examples": {
                    "type": "array",
                    "items": _obj({"situation": {"type": "string"}, "good": {"type": "string"}, "bad": {"type": "string"}}),
                },
            }
        ),
    }
)
