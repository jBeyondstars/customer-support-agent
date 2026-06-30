import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import class_row

# Every query in here filters on customer_id. The id always comes from the
# logged-in session, never from the model, so a customer can't reach someone
# else's orders by asking nicely.


@dataclass
class OrderSummary:
    number: str
    status: str
    placed_at: datetime
    total: Decimal
    shipment_status: str | None
    items: str


@dataclass
class OrderItem:
    sku: str
    name: str
    category: str
    quantity: int
    unit_price: Decimal


@dataclass
class ReturnRequest:
    skus: list[str]
    reason: str
    status: str
    created_at: datetime


@dataclass
class Order:
    id: int
    number: str
    status: str
    placed_at: datetime
    total: Decimal
    carrier: str | None
    tracking_number: str | None
    shipment_status: str | None
    estimated_delivery: date | None
    delivered_at: datetime | None
    items: list[OrderItem] = field(default_factory=list)
    returns: list[ReturnRequest] = field(default_factory=list)


def normalize_order_number(raw: str) -> str:
    """'10088', 'nc10088' and ' NC-10088 ' all become 'NC-10088'."""
    digits = re.sub(r"\D", "", raw)
    return f"NC-{digits}"


def list_orders(
    conn: psycopg.Connection, customer_id: int, status: str | None = None, limit: int = 10
) -> list[OrderSummary]:
    with conn.cursor(row_factory=class_row(OrderSummary)) as cur:
        cur.execute(
            """
            select o.number, o.status, o.placed_at, o.total,
                   s.status as shipment_status,
                   string_agg(
                       p.name || case when i.quantity > 1 then ' x' || i.quantity else '' end,
                       ', ' order by p.name
                   ) as items
            from orders o
            left join shipments s on s.order_id = o.id
            join order_items i on i.order_id = o.id
            join products p on p.sku = i.sku
            where o.customer_id = %(customer_id)s
              and (%(status)s::text is null or o.status = %(status)s)
            group by o.id, s.status
            order by o.placed_at desc
            limit %(limit)s
            """,
            {"customer_id": customer_id, "status": status, "limit": limit},
        )
        return cur.fetchall()


def get_order(conn: psycopg.Connection, customer_id: int, order_number: str) -> Order | None:
    with conn.cursor(row_factory=class_row(Order)) as cur:
        order = cur.execute(
            """
            select o.id, o.number, o.status, o.placed_at, o.total,
                   s.carrier, s.tracking_number, s.status as shipment_status,
                   s.estimated_delivery, s.delivered_at
            from orders o
            left join shipments s on s.order_id = o.id
            where o.number = %s and o.customer_id = %s
            """,
            (normalize_order_number(order_number), customer_id),
        ).fetchone()
    if order is None:
        return None

    with conn.cursor(row_factory=class_row(OrderItem)) as cur:
        order.items = cur.execute(
            "select i.sku, p.name, p.category, i.quantity, i.unit_price"
            " from order_items i join products p on p.sku = i.sku"
            " where i.order_id = %s order by p.name",
            (order.id,),
        ).fetchall()

    with conn.cursor(row_factory=class_row(ReturnRequest)) as cur:
        order.returns = cur.execute(
            "select skus, reason, status, created_at from return_requests"
            " where order_id = %s order by created_at",
            (order.id,),
        ).fetchall()

    return order


def create_return_request(
    conn: psycopg.Connection, customer_id: int, order_number: str, skus: list[str], reason: str
) -> int | None:
    row = conn.execute(
        """
        insert into return_requests (order_id, skus, reason)
        select id, %s, %s from orders where number = %s and customer_id = %s
        returning id
        """,
        (skus, reason, normalize_order_number(order_number), customer_id),
    ).fetchone()
    return row[0] if row else None


def create_ticket(
    conn: psycopg.Connection, customer_id: int, thread_id: str | None, summary: str, priority: str
) -> int:
    return conn.execute(
        "insert into support_tickets (customer_id, thread_id, summary, priority)"
        " values (%s, %s, %s, %s) returning id",
        (customer_id, thread_id, summary, priority),
    ).fetchone()[0]
