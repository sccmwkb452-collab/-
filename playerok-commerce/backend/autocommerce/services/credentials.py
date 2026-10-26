"""Integration credentials.

Environment variables win; values entered in the web panel are stored as one
Fernet-encrypted JSON blob per provider with a masked preview for display.
Secrets are never returned by the API and never sent to Telegram.
"""

from __future__ import annotations

import json
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import IntegrationCredential
from ..integrations.suppliers.base import CredentialField
from ..shared import crypto
from ..shared.masking import mask_secret
from ..shared.timeutil import utcnow
from .audit import Actor, audit


async def get_credentials(session: AsyncSession, provider: str, fields: tuple[CredentialField, ...]) -> dict[str, str]:
    stored: dict[str, str] = {}
    row = (await session.execute(select(IntegrationCredential).where(IntegrationCredential.provider == provider))).scalar_one_or_none()
    if row is not None:
        stored = json.loads(crypto.decrypt(row.fields_enc))
    out: dict[str, str] = {}
    for field in fields:
        env_value = os.environ.get(field.env, "").strip() if field.env else ""
        value = env_value or stored.get(field.name, "")
        if value:
            out[field.name] = value
    return out


async def describe(session: AsyncSession, provider: str, fields: tuple[CredentialField, ...]) -> list[dict]:
    """Masked view for the panel: where each value comes from, never the value."""
    row = (await session.execute(select(IntegrationCredential).where(IntegrationCredential.provider == provider))).scalar_one_or_none()
    preview = row.preview if row else {}
    out = []
    for field in fields:
        from_env = bool(field.env and os.environ.get(field.env, "").strip())
        out.append(
            {
                "name": field.name,
                "label": field.label,
                "secret": field.secret,
                "help": field.help,
                "env": field.env,
                "source": "env" if from_env else ("panel" if field.name in preview else None),
                "preview": ("из переменной окружения" if from_env else preview.get(field.name, "")),
            }
        )
    return out


async def save_credentials(
    session: AsyncSession, provider: str, fields: tuple[CredentialField, ...], values: dict[str, str], actor: Actor
) -> None:
    allowed = {f.name: f for f in fields}
    row = (await session.execute(select(IntegrationCredential).where(IntegrationCredential.provider == provider))).scalar_one_or_none()
    current: dict[str, str] = json.loads(crypto.decrypt(row.fields_enc)) if row else {}
    for name, value in values.items():
        if name not in allowed:
            continue
        value = (value or "").strip()
        if value:
            current[name] = value[:500]
        else:
            current.pop(name, None)
    preview = {k: (mask_secret(v) if allowed[k].secret else v) for k, v in current.items()}
    blob = crypto.encrypt(json.dumps(current))
    if row is None:
        session.add(IntegrationCredential(provider=provider, fields_enc=blob, preview=preview, updated_by=actor.label, rotated_at=utcnow()))
    else:
        row.fields_enc = blob
        row.preview = preview
        row.updated_by = actor.label
        row.rotated_at = utcnow()
    await audit(session, actor, "credentials.update", entity_type="integration", entity_id=provider, details={"fields": sorted(values)})


async def delete_credentials(session: AsyncSession, provider: str, actor: Actor) -> None:
    row = (await session.execute(select(IntegrationCredential).where(IntegrationCredential.provider == provider))).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
    await audit(session, actor, "credentials.delete", entity_type="integration", entity_id=provider)


async def rotate_encryption(session: AsyncSession) -> int:
    """Re-encrypt all stored credentials with the first CREDENTIALS_KEY."""
    rows = (await session.execute(select(IntegrationCredential))).scalars().all()
    for row in rows:
        row.fields_enc = crypto.rotate(row.fields_enc)
    return len(rows)
