from dataclasses import dataclass
from datetime import date, timedelta

from support_agent.shop.repository import Order, OrderItem

# Same rules as data/kb/returns-and-refunds.md. They live in code because date
# arithmetic and "is this category excluded" are exactly what an LLM gets wrong.
RETURN_WINDOW_DAYS = 30

NON_RETURNABLE = {
    "nutrition": "Nutrition products can't be returned.",
    "gift_card": "Gift cards can't be returned.",
    "custom_build": "Custom builds can only come back if they're faulty (warranty claim).",
}

BIKE_CONDITIONS = (
    "Less than 20 km ridden, pedals off, packed in its original box. "
    "The €49 pickup fee is taken off the refund unless the bike is faulty."
)

CONDITIONS = {
    "ebike": BIKE_CONDITIONS,
    "bike": BIKE_CONDITIONS,
    "battery": "Only if the seal on the box is still intact.",
}


@dataclass
class ItemCheck:
    sku: str
    name: str
    eligible: bool
    note: str


@dataclass
class ReturnCheck:
    order_number: str
    deadline: date | None
    items: list[ItemCheck]

    @property
    def eligible_skus(self) -> list[str]:
        return [item.sku for item in self.items if item.eligible]


def check_return(order: Order, today: date) -> ReturnCheck:
    if order.status != "delivered" or order.delivered_at is None:
        if order.status == "processing":
            note = "The order hasn't shipped yet, so it can still be cancelled instead."
        else:
            note = f"The order is {order.status}, a return can only be requested after delivery."
        return ReturnCheck(order.number, None, [refuse(item, note) for item in order.items])

    deadline = order.delivered_at.date() + timedelta(days=RETURN_WINDOW_DAYS)
    already_returned = {sku for request in order.returns for sku in request.skus}

    items = []
    for item in order.items:
        if today > deadline:
            items.append(refuse(item, f"The 30-day return window closed on {deadline}."))
        elif item.sku in already_returned:
            items.append(refuse(item, "There's already a return request for this item."))
        elif item.category in NON_RETURNABLE:
            items.append(refuse(item, NON_RETURNABLE[item.category]))
        else:
            items.append(ItemCheck(item.sku, item.name, True, conditions(item)))
    return ReturnCheck(order.number, deadline, items)


def conditions(item: OrderItem) -> str:
    if "helmet" in item.name.lower():
        return "Only if it has never been worn, stickers on and pads still in their bag."
    return CONDITIONS.get(item.category, "Unused, in its original packaging with the labels on.")


def refuse(item: OrderItem, note: str) -> ItemCheck:
    return ItemCheck(item.sku, item.name, False, note)
