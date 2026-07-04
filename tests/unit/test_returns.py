from datetime import UTC, date, datetime
from decimal import Decimal

from support_agent.shop.repository import Order, OrderItem, ReturnRequest
from support_agent.shop.returns import check_return

DELIVERED = datetime(2026, 9, 1, 15, 30, tzinfo=UTC)


def item(sku: str, category: str, name: str = "Thing") -> OrderItem:
    return OrderItem(sku, name, category, 1, Decimal("10.00"))


def order(*items: OrderItem, status: str = "delivered", returns=()) -> Order:
    return Order(
        id=1,
        number="NC-10001",
        status=status,
        placed_at=datetime(2026, 8, 28, tzinfo=UTC),
        total=Decimal("10.00"),
        carrier="Colissimo",
        tracking_number="6A00000000000",
        shipment_status="delivered" if status == "delivered" else None,
        estimated_delivery=None,
        delivered_at=DELIVERED if status == "delivered" else None,
        items=list(items),
        returns=list(returns),
    )


def test_window_closes_30_days_after_delivery():
    pump = order(item("PMP-FLR-01", "accessory"))

    last_day = check_return(pump, today=date(2026, 10, 1))
    too_late = check_return(pump, today=date(2026, 10, 2))

    assert last_day.deadline == date(2026, 10, 1)
    assert last_day.eligible_skus == ["PMP-FLR-01"]
    assert too_late.eligible_skus == []
    assert "closed on 2026-10-01" in too_late.items[0].note


def test_nutrition_and_gift_cards_are_never_returnable():
    check = check_return(
        order(item("NUT-GEL-12", "nutrition"), item("GFT-050", "gift_card"), item("TIR", "part")),
        today=date(2026, 9, 5),
    )

    assert check.eligible_skus == ["TIR"]


def test_bike_return_is_allowed_with_conditions():
    check = check_return(order(item("NC-URB-E5", "ebike")), today=date(2026, 9, 5))

    assert check.items[0].eligible
    assert "20 km" in check.items[0].note
    assert "€49" in check.items[0].note


def test_order_still_processing_points_to_cancellation():
    check = check_return(
        order(item("NC-KID-K1", "bike"), status="processing"), today=date(2026, 9, 5)
    )

    assert check.eligible_skus == []
    assert "cancelled" in check.items[0].note


def test_item_already_in_a_return_request_cannot_be_returned_twice():
    previous = ReturnRequest(["HLM-URB-01"], "too small", "requested", DELIVERED)
    check = check_return(
        order(item("HLM-URB-01", "accessory", "Urban helmet"), item("LGT-SET-01", "accessory"),
              returns=[previous]),
        today=date(2026, 9, 5),
    )  # fmt: skip

    assert check.eligible_skus == ["LGT-SET-01"]
