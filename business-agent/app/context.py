"""Контейнер зависимостей, который создаётся один раз при старте."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.llm import LLMClient
from app.config import Settings
from app.deals.manager import DealManager
from app.media.analyzer import MediaAnalyzer
from app.nft.pages import GiftPageClient
from app.trading.registry import AdapterFactory


@dataclass
class AppContext:
    settings: Settings
    bot: Bot
    sessions: async_sessionmaker[AsyncSession]
    llm: LLMClient | None
    media: MediaAnalyzer
    trade_adapters: AdapterFactory
    deals: DealManager
    gifts: GiftPageClient
    business: Any = None  # BusinessService, задаётся после создания
    outreach: Any = None  # OutreachService
