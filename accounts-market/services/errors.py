class ShopError(Exception):
    """Business error with a message that is safe to show to the user."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class InsufficientFunds(ShopError):
    def __init__(self, needed: int = 0) -> None:
        super().__init__("Недостаточно средств на балансе")
        self.needed = needed


class OutOfStock(ShopError):
    def __init__(self, available: int = 0) -> None:
        super().__init__(f"В наличии только {available} шт." if available else "Товар закончился")
        self.available = available


class ProductUnavailable(ShopError):
    def __init__(self) -> None:
        super().__init__("Товар больше недоступен")


class PriceChanged(ShopError):
    def __init__(self, new_price: int) -> None:
        super().__init__("Цена товара изменилась")
        self.new_price = new_price


class AccessRestricted(ShopError):
    def __init__(self) -> None:
        super().__init__("Доступ к покупкам ограничен")
