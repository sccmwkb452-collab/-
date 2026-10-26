"""Truthful listing titles and descriptions per category template.

Rules: state the region, delivery time, what the buyer must provide and the
activation limits; no «100 % гарантия», no invented brand claims, no
promises the system cannot verify.
"""

from __future__ import annotations

from ..database.models import Product

TITLE_LIMIT = 100
DESCRIPTION_LIMIT = 2000

FORBIDDEN_PHRASES = ("100% гарант", "100 % гарант", "официальный представитель", "официальный дилер", "без риска", "лучшая цена")


def _face(product: Product) -> str:
    if product.face_value is None:
        return ""
    return f"{product.face_value.normalize():f} {product.face_currency or ''}".strip()


def title_for(product: Product, template: str | None = None) -> str:
    template = template or product.category.listing_template
    face = _face(product)
    if template == "giftcard":
        parts = [product.name]
        if face and face not in product.name:
            parts.append(face)
        if product.region:
            parts.append(f"регион {product.region}")
        title = " | ".join(parts)
    elif template in ("telegram_stars", "telegram_premium"):
        title = f"{product.name} | на ваш аккаунт по username"
    elif template == "promotion":
        title = f"{product.name} | по ссылке"
    else:
        title = product.name
    return title[:TITLE_LIMIT]


def description_for(product: Product, template: str | None = None) -> str:
    template = template or product.category.listing_template
    lines: list[str] = []
    face = _face(product)
    if template == "giftcard":
        lines.append(f"Цифровой код: {product.name}{f' номиналом {face}' if face else ''}.")
        lines.append(
            f"Регион активации: {product.region or 'уточняйте перед покупкой'}. Код активируется только на аккаунте этого региона."
        )
    elif template == "telegram_stars":
        lines.append(f"{product.name}. Зачисление на ваш аккаунт Telegram через официальную покупку для другого пользователя (Fragment).")
        lines.append("Пароль и вход в аккаунт не нужны — только ваш username.")
    elif template == "telegram_premium":
        lines.append(f"{product.name}. Подписка оформляется подарком на ваш аккаунт Telegram через Fragment.")
        lines.append("Пароль и вход в аккаунт не нужны — только ваш username.")
    elif template == "promotion":
        lines.append(f"Услуга: {product.name}.")
        lines.append(
            "Выполняется по ссылке, которую вы пришлёте после оплаты. Скорость и результат зависят от платформы; часть аудитории может отписаться со временем."
        )
    else:
        lines.append(product.name + ".")
    if product.description:
        lines.append(product.description.strip())
    lines.append(f"Срок выдачи: {product.delivery_time}.")
    if product.required_buyer_data:
        lines.append(f"После оплаты пришлите: {product.required_buyer_data}.")
    if product.activation_notes:
        lines.append(f"Ограничения: {product.activation_notes.strip()}")
    if product.buyer_instructions:
        lines.append(f"Как получить: {product.buyer_instructions.strip()}")
    lines.append("Если что-то пошло не так — напишите в чат сделки до подтверждения, разберёмся.")
    return "\n\n".join(lines)[:DESCRIPTION_LIMIT]


def check_text(title: str, description: str) -> list[str]:
    problems = []
    if not 5 <= len(title) <= TITLE_LIMIT:
        problems.append(f"Название должно быть от 5 до {TITLE_LIMIT} символов")
    if len(description) < 30:
        problems.append("Описание слишком короткое: укажите регион, срок выдачи и условия получения")
    if len(description) > DESCRIPTION_LIMIT:
        problems.append(f"Описание длиннее {DESCRIPTION_LIMIT} символов")
    lowered = f"{title}\n{description}".lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            problems.append(f"Недопустимое обещание: «{phrase}»")
    if "срок" not in lowered and "выдач" not in lowered:
        problems.append("В описании нет срока выдачи")
    return problems
