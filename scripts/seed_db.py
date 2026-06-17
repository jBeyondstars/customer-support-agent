"""Reset the shop tables and fill them with demo data.

Customers 1 to 5 are hand-written scenarios used by the demo and the evals,
everyone else is random but reproducible (fixed seed). Dates are relative to
now so the 30-day return window keeps making sense whenever this runs.
"""

import random
import string
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
from faker import Faker

from support_agent.config import get_settings

SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

PRODUCTS = [
    ("NC-URB-E5", "Nomad Urban E5", "ebike", "1890.00"),
    ("NC-TRL-E7", "Nomad Trail E7", "ebike", "3290.00"),
    ("NC-CRG-E9", "Nomad Cargo E9", "ebike", "4490.00"),
    ("NC-GRV-G3", "Nomad Gravel G3", "bike", "1290.00"),
    ("NC-GRV-G3X", "Nomad Gravel G3 custom build", "custom_build", "2150.00"),
    ("NC-CTY-C2", "Nomad City C2", "bike", "690.00"),
    ("NC-KID-K1", "Nomad Kids K1", "bike", "390.00"),
    ("HLM-URB-01", "Urban helmet", "accessory", "59.00"),
    ("LCK-U-02", "Shackle Pro U-lock", "accessory", "75.00"),
    ("LGT-SET-01", "Front and rear light set", "accessory", "45.00"),
    ("BAG-PAN-20", "Pannier bag 20L", "accessory", "69.00"),
    ("PMP-FLR-01", "Floor pump", "accessory", "39.00"),
    ("BAT-504", "Spare battery 504 Wh", "battery", "549.00"),
    ("TUB-700-02", "Inner tubes 700x35 (pack of 2)", "part", "14.00"),
    ("TIR-GRV-40", "Gravel tyre 700x40", "part", "42.00"),
    ("CHN-10S", "Chain 10-speed", "part", "29.00"),
    ("PAD-HYD-01", "Hydraulic brake pads", "part", "18.00"),
    ("JKT-RAIN-01", "Rain jacket", "apparel", "89.00"),
    ("GLV-WIN-01", "Winter gloves", "apparel", "35.00"),
    ("NUT-GEL-12", "Energy gels (box of 12)", "nutrition", "24.00"),
    ("NUT-BAR-10", "Oat bars (box of 10)", "nutrition", "19.00"),
    ("GFT-050", "Gift card 50 EUR", "gift_card", "50.00"),
    ("GFT-100", "Gift card 100 EUR", "gift_card", "100.00"),
]

PRICES = {sku: Decimal(price) for sku, _, _, price in PRODUCTS}
CATEGORIES = {sku: category for sku, _, category, _ in PRODUCTS}
BIKES = [sku for sku, _, category, _ in PRODUCTS if category in ("ebike", "bike")]
ACCESSORIES = [sku for sku, _, category, _ in PRODUCTS if category == "accessory"]
SMALL_ITEMS = [
    sku for sku, _, category, _ in PRODUCTS if category not in ("ebike", "bike", "custom_build")
]

CITIES = [
    "Paris", "Lyon", "Villeurbanne", "Grenoble", "Annecy", "Marseille", "Toulouse", "Bordeaux",
    "Nantes", "Rennes", "Lille", "Strasbourg", "Dijon", "Montpellier", "Tours", "Clermont-Ferrand",
]  # fmt: skip

SCENARIO_CUSTOMERS = [
    ("camille.martin@example.com", "Camille", "Martin", "Lyon"),
    ("lucas.bernard@example.com", "Lucas", "Bernard", "Nantes"),
    ("emma.petit@example.com", "Emma", "Petit", "Bordeaux"),
    ("hugo.durand@example.com", "Hugo", "Durand", "Grenoble"),
    ("lea.moreau@example.com", "Léa", "Moreau", "Lille"),
]


@dataclass
class Shipment:
    carrier: str
    status: str
    shipped_at: datetime
    estimated_delivery: datetime
    delivered_at: datetime | None


@dataclass
class Order:
    customer_id: int
    placed_at: datetime
    items: list[tuple[str, int]]
    status: str
    shipment: Shipment | None = None

    @property
    def is_bike_order(self) -> bool:
        return any(CATEGORIES[sku] in ("ebike", "bike", "custom_build") for sku, _ in self.items)

    @property
    def total(self) -> Decimal:
        subtotal = sum(PRICES[sku] * qty for sku, qty in self.items)
        if not self.is_bike_order and subtotal < 60:
            subtotal += Decimal("5.90")
        return subtotal


def scenario_orders(now: datetime) -> list[Order]:
    def ago(days: float) -> datetime:
        return now - timedelta(days=days)

    def delivered(carrier: str, shipped: float, arrived: float) -> Shipment:
        return Shipment(carrier, "delivered", ago(shipped), ago(arrived), ago(arrived))

    return [
        # Camille: e-bike delivered 12 days ago, so it can still be returned
        Order(1, ago(20), [("NC-URB-E5", 1), ("HLM-URB-01", 1)], "delivered",
              delivered("GEODIS", 15, 12)),
        Order(1, ago(120), [("LGT-SET-01", 1), ("PMP-FLR-01", 1)], "delivered",
              delivered("Colissimo", 119, 116)),
        # Lucas: parcel stuck in transit, the estimated delivery date is long gone
        Order(2, ago(10), [("LCK-U-02", 1), ("BAG-PAN-20", 1)], "shipped",
              Shipment("Colissimo", "delayed", ago(9), ago(6), None)),
        Order(2, ago(200), [("JKT-RAIN-01", 1)], "delivered", delivered("DPD", 199, 197)),
        # Emma: gravel bike outside the return window, and a mixed order with nutrition
        Order(3, ago(50), [("NC-GRV-G3", 1)], "delivered", delivered("GEODIS", 46, 45)),
        Order(3, ago(8), [("NUT-GEL-12", 1), ("TIR-GRV-40", 2), ("TUB-700-02", 1)], "delivered",
              delivered("Colissimo", 7, 5)),
        # Hugo: delivered yesterday (inside the 48h damage window) and a kids bike being built
        Order(4, ago(5), [("HLM-URB-01", 1), ("LGT-SET-01", 1)], "delivered",
              delivered("Colissimo", 4, 1)),
        Order(4, ago(2), [("NC-KID-K1", 1)], "processing"),
    ]  # fmt: skip


def random_basket(rng: random.Random) -> list[tuple[str, int]]:
    roll = rng.random()
    if roll < 0.04:
        return [("NC-GRV-G3X", 1)]
    if roll < 0.25:
        extras = rng.sample(ACCESSORIES, k=rng.randint(0, 2))
        return [(rng.choice(BIKES), 1)] + [(sku, 1) for sku in extras]
    return [(sku, rng.choice([1, 1, 1, 2])) for sku in rng.sample(SMALL_ITEMS, k=rng.randint(1, 3))]


def random_order(rng: random.Random, now: datetime, customer_id: int) -> Order:
    recent = rng.random() < 0.15
    placed_at = now - timedelta(days=rng.uniform(0.5, 10) if recent else rng.uniform(10, 540))
    order = Order(customer_id, placed_at, random_basket(rng), "processing")

    if rng.random() < 0.04:
        order.status = "cancelled"
        return order

    if any(sku == "NC-GRV-G3X" for sku, _ in order.items):
        build_days = rng.randint(21, 28)
    elif order.is_bike_order:
        build_days = rng.randint(3, 5)
    else:
        build_days = rng.uniform(0.2, 1.2)

    carrier = "GEODIS" if order.is_bike_order else rng.choice(["Colissimo", "Colissimo", "DPD"])
    shipped_at = placed_at + timedelta(days=build_days)
    transit_days = rng.randint(3, 6) if order.is_bike_order else rng.randint(2, 3)
    delivered_at = shipped_at + timedelta(days=transit_days)

    if shipped_at > now:
        return order
    if delivered_at > now:
        order.status = "shipped"
        order.shipment = Shipment(carrier, "in_transit", shipped_at, delivered_at, None)
    else:
        order.status = "delivered"
        order.shipment = Shipment(carrier, "delivered", shipped_at, delivered_at, delivered_at)
    return order


def tracking_number(rng: random.Random, carrier: str) -> str:
    prefix, length = {"Colissimo": ("6A", 11), "DPD": ("", 14)}.get(carrier, ("GE", 10))
    return prefix + "".join(rng.choices(string.digits, k=length))


def ascii_slug(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return plain.lower().replace(" ", "-").replace("'", "")


def random_customers(fake: Faker, count: int) -> list[tuple[str, str, str, str]]:
    customers = []
    for i in range(count):
        first, last = fake.first_name(), fake.last_name()
        email = f"{ascii_slug(first)}.{ascii_slug(last)}{i}@example.net"
        # Faker's fr_FR cities are made up ("Saint Jeannenec"), real ones read better in a demo.
        customers.append((email, first, last, fake.random_element(CITIES)))
    return customers


def main() -> None:
    rng = random.Random(42)
    fake = Faker("fr_FR")
    fake.seed_instance(42)
    now = datetime.now(UTC)

    customers = SCENARIO_CUSTOMERS + random_customers(fake, 30)
    orders = scenario_orders(now)
    for customer_id in range(len(SCENARIO_CUSTOMERS) + 1, len(customers) + 1):
        for _ in range(rng.choice([0, 1, 2, 2, 3, 4, 5, 7])):
            orders.append(random_order(rng, now, customer_id))
    # Order numbers follow the order date, like they would in a real shop.
    orders.sort(key=lambda o: o.placed_at)

    with psycopg.connect(get_settings().database_url) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        conn.execute(
            "truncate customers, products, orders, order_items, shipments, return_requests,"
            " support_tickets, threads restart identity cascade"
        )

        with conn.cursor() as cur:
            cur.executemany(
                "insert into customers (email, first_name, last_name, city)"
                " values (%s, %s, %s, %s)",
                customers,
            )
            cur.executemany(
                "insert into products (sku, name, category, price) values (%s, %s, %s, %s)",
                PRODUCTS,
            )

            for number, order in enumerate(orders, start=10001):
                cur.execute(
                    "insert into orders (number, customer_id, status, placed_at, total)"
                    " values (%s, %s, %s, %s, %s) returning id",
                    (f"NC-{number}", order.customer_id, order.status, order.placed_at, order.total),
                )
                order_id = cur.fetchone()[0]
                cur.executemany(
                    "insert into order_items (order_id, sku, quantity, unit_price)"
                    " values (%s, %s, %s, %s)",
                    [(order_id, sku, qty, PRICES[sku]) for sku, qty in order.items],
                )
                if s := order.shipment:
                    cur.execute(
                        "insert into shipments (order_id, carrier, tracking_number, status,"
                        " shipped_at, estimated_delivery, delivered_at)"
                        " values (%s, %s, %s, %s, %s, %s, %s)",
                        (order_id, s.carrier, tracking_number(rng, s.carrier), s.status,
                         s.shipped_at, s.estimated_delivery.date(), s.delivered_at),
                    )  # fmt: skip

            # A few old refunded returns so order histories don't look too clean.
            cur.execute(
                "select o.id, array_agg(i.sku) from orders o"
                " join order_items i on i.order_id = o.id"
                " join products p on p.sku = i.sku"
                " where o.customer_id > 5 and o.status = 'delivered'"
                " and o.placed_at < now() - interval '60 days'"
                " and p.category in ('accessory', 'apparel', 'part')"
                " group by o.id order by o.id"
            )
            candidates = cur.fetchall()
            cur.executemany(
                "insert into return_requests (order_id, skus, reason, status, created_at)"
                " select %s, %s, %s, 'refunded', delivered_at + interval '6 days'"
                " from shipments where order_id = %s",
                [
                    (order_id, skus[:1], reason, order_id)
                    for (order_id, skus), reason in zip(
                        rng.sample(candidates, k=6),
                        ["wrong size", "changed my mind", "doesn't fit my bike",
                         "arrived too late", "colour not as pictured", "ordered twice"],
                        strict=True,
                    )
                ],
            )  # fmt: skip

        counts = {
            table: conn.execute(f"select count(*) from {table}").fetchone()[0]
            for table in ("customers", "products", "orders", "order_items", "shipments",
                          "return_requests")
        }  # fmt: skip
        print(", ".join(f"{n} {table}" for table, n in counts.items()))

        print("\nScenario customers:")
        rows = conn.execute(
            "select c.id, c.first_name, c.last_name,"
            " coalesce(string_agg(o.number || ' ' || o.status, ', ' order by o.placed_at), '-')"
            " from customers c left join orders o on o.customer_id = c.id"
            " where c.id <= 5 group by c.id order by c.id"
        ).fetchall()
        for customer_id, first, last, summary in rows:
            print(f"  {customer_id}  {first} {last}: {summary}")


if __name__ == "__main__":
    main()
