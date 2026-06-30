import pytest

from support_agent.shop.repository import create_return_request, get_order, list_orders

pytestmark = pytest.mark.integration

# Scenario customers from scripts/seed_db.py
CAMILLE, LUCAS, LEA = 1, 2, 5


def order_numbers(conn, customer_id: int) -> list[str]:
    rows = conn.execute(
        "select number from orders where customer_id = %s order by placed_at", (customer_id,)
    ).fetchall()
    return [number for (number,) in rows]


def test_order_from_another_customer_is_not_found(conn):
    camille_order = order_numbers(conn, CAMILLE)[0]

    assert get_order(conn, LUCAS, camille_order) is None
    assert get_order(conn, CAMILLE, camille_order) is not None


def test_list_orders_only_returns_own_orders(conn):
    listed = {order.number for order in list_orders(conn, CAMILLE)}

    assert listed == set(order_numbers(conn, CAMILLE))


def test_customer_without_orders_gets_an_empty_list(conn):
    assert list_orders(conn, LEA) == []


def test_delayed_order_comes_with_items_and_tracking(conn):
    order = get_order(conn, LUCAS, order_numbers(conn, LUCAS)[-1])

    assert order.shipment_status == "delayed"
    assert order.tracking_number.startswith("6A")
    assert {item.sku for item in order.items} == {"LCK-U-02", "BAG-PAN-20"}


def test_order_number_typed_loosely_still_matches(conn):
    number = order_numbers(conn, CAMILLE)[0]

    assert get_order(conn, CAMILLE, number.lower().replace("-", " ")) is not None


def test_return_on_someone_elses_order_is_not_created(conn):
    camille_order = order_numbers(conn, CAMILLE)[0]

    assert create_return_request(conn, LUCAS, camille_order, ["HLM-URB-01"], "test") is None
    assert get_order(conn, CAMILLE, camille_order).returns == []
