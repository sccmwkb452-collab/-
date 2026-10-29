from aiogram import Router

from app.bot import inputs
from app.bot.handlers import (
    admin,
    agent,
    ai_settings,
    business_updates,
    deals,
    media,
    parsers,
    settings,
    start,
    stats,
    templates,
    trade,
)
from app.bot.middlewares import PanelMiddleware


def _detach(router: Router) -> Router:
    """Роутеры разделов — модульные синглтоны; при повторной сборке (тесты) отвязываем их от старого родителя."""
    parent = router.parent_router
    if parent is not None:
        parent.sub_routers.remove(router)
        router._parent_router = None
    return router


def build_routers(ctx) -> list[Router]:
    panel = Router(name="panel")
    panel.message.middleware(PanelMiddleware(ctx))
    panel.callback_query.middleware(PanelMiddleware(ctx))
    # Порядок важен: состояния ввода раньше общих обработчиков.
    panel.include_routers(*map(_detach, (
        inputs.router, admin.router, trade.router, parsers.router, media.router, start.router, agent.router,
        templates.router, ai_settings.router, deals.router, stats.router, settings.router,
    )))
    return [business_updates.setup(ctx), panel]
