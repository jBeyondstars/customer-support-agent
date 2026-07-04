from datetime import date
from typing import Literal

from langchain.tools import ToolRuntime, tool

from support_agent.agent.state import Context
from support_agent.db import get_pool
from support_agent.rag.retriever import search
from support_agent.shop import repository
from support_agent.shop.repository import Order, OrderSummary
from support_agent.shop.returns import check_return

Runtime = ToolRuntime[Context]


@tool(response_format="content_and_artifact")
def search_knowledge_base(query: str) -> tuple[str, list[dict]]:
    """Search the Nomad Cycles help pages: shipping, returns, damaged parcels, warranty,
    payment, products, sizes, e-bike care and error codes, workshop, contact.
    The pages are in English, so write the query in English whatever language the
    customer uses."""
    with get_pool().connection() as conn:
        results = search(conn, query)
    if not results:
        return "Nothing relevant in the help pages.", []

    content = "\n\n".join(f"[{i}] {r.content}" for i, r in enumerate(results, start=1))
    sources = [{"title": r.title, "section": r.section, "document": r.document} for r in results]
    return content, sources


@tool
def list_my_orders(
    runtime: Runtime,
    status: Literal["processing", "shipped", "delivered", "cancelled"] | None = None,
) -> str:
    """List the customer's 10 most recent orders, newest first. Optionally filter by status."""
    with get_pool().connection() as conn:
        orders = repository.list_orders(conn, runtime.context.customer_id, status)
    if not orders:
        return "No orders found on this account."
    return "\n".join(format_summary(order) for order in orders)


@tool
def get_order_details(runtime: Runtime, order_number: str) -> str:
    """Get one order of the customer: items with their SKUs, prices, carrier, tracking
    number, delivery dates and any return requests."""
    with get_pool().connection() as conn:
        order = repository.get_order(conn, runtime.context.customer_id, order_number)
    if order is None:
        return not_found(order_number)
    return format_order(order)


@tool
def check_return_eligibility(runtime: Runtime, order_number: str) -> str:
    """Tell which items of an order can be returned, until when, and under which conditions.
    Always check this before offering a return."""
    with get_pool().connection() as conn:
        order = repository.get_order(conn, runtime.context.customer_id, order_number)
    if order is None:
        return not_found(order_number)

    check = check_return(order, date.today())
    lines = [f"Order {check.order_number}. Return deadline: {check.deadline or 'n/a'}."]
    for item in check.items:
        verdict = "returnable" if item.eligible else "NOT returnable"
        lines.append(f"- {item.name} ({item.sku}): {verdict}. {item.note}")
    return "\n".join(lines)


@tool
def create_return_request(runtime: Runtime, order_number: str, skus: list[str], reason: str) -> str:
    """Open a return for some items of an order. Only call it once the customer has told you
    which items and why. The app asks the customer to confirm before it goes through, so
    don't ask for confirmation yourself."""
    customer_id = runtime.context.customer_id
    with get_pool().connection() as conn:
        order = repository.get_order(conn, customer_id, order_number)
        if order is None:
            return not_found(order_number)

        # Re-check here: the model may skip check_return_eligibility, the rules can't be skipped.
        allowed = check_return(order, date.today()).eligible_skus
        refused = [sku for sku in skus if sku not in allowed]
        if not skus:
            return "Nothing was created: no items were given."
        if refused:
            return (
                f"Nothing was created. These items can't be returned: {', '.join(refused)}. "
                "Use check_return_eligibility to see why."
            )

        request_id = repository.create_return_request(conn, customer_id, order.number, skus, reason)
    return (
        f"Return request #{request_id} created for {', '.join(skus)} on order {order.number}. "
        "The customer gets the return instructions by email within one working day "
        "(prepaid label, or a GEODIS pickup for bikes)."
    )


@tool
def escalate_to_human(
    runtime: Runtime, summary: str, priority: Literal["low", "normal", "high"] = "normal"
) -> str:
    """Hand the conversation over to the support team. Use it for anything you can't settle
    yourself: lost or damaged parcels, warranty claims, cancellations, upset customers,
    questions the help pages don't answer. Write a summary the team can act on without
    reading the whole chat (order number, problem, what the customer wants)."""
    thread_id = runtime.config.get("configurable", {}).get("thread_id")
    with get_pool().connection() as conn:
        ticket_id = repository.create_ticket(
            conn, runtime.context.customer_id, thread_id, summary, priority
        )
    return f"Ticket #{ticket_id} created. The team replies by email within one working day."


def format_summary(order: OrderSummary) -> str:
    shipment = f" (carrier: {order.shipment_status})" if order.shipment_status == "delayed" else ""
    return (
        f"{order.number} | placed {order.placed_at:%Y-%m-%d} | {order.status}{shipment}"
        f" | €{order.total} | {order.items}"
    )


def format_order(order: Order) -> str:
    lines = [
        f"Order {order.number}, placed {order.placed_at:%Y-%m-%d}, status {order.status}, "
        f"total €{order.total}",
        "Items:",
        *[
            f"- {item.name} (SKU {item.sku}) x{item.quantity}, €{item.unit_price} each"
            for item in order.items
        ],
    ]
    if order.carrier:
        delivered = f"{order.delivered_at:%Y-%m-%d}" if order.delivered_at else "not yet"
        lines.append(
            f"Shipment: {order.carrier}, tracking {order.tracking_number}, "
            f"status {order.shipment_status}, estimated delivery {order.estimated_delivery}, "
            f"delivered {delivered}"
        )
    else:
        lines.append("Shipment: not shipped yet")
    for request in order.returns:
        lines.append(
            f"Return request from {request.created_at:%Y-%m-%d}: {', '.join(request.skus)}, "
            f"status {request.status}"
        )
    return "\n".join(lines)


def not_found(order_number: str) -> str:
    # Same answer whether the order doesn't exist or belongs to someone else.
    return f"No order {repository.normalize_order_number(order_number)} on this customer's account."


TOOLS = [
    search_knowledge_base,
    list_my_orders,
    get_order_details,
    check_return_eligibility,
    create_return_request,
    escalate_to_human,
]

# Tools that change something for the customer and need their explicit go-ahead.
NEEDS_CONFIRMATION = {create_return_request.name}
