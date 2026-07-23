"""Demo UI. It only talks to the API, like any other client would.

streamlit run src/support_agent/ui/app.py
"""

import json
import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

DEMO_CUSTOMERS = {
    1: "Camille, e-bike delivered 12 days ago",
    2: "Lucas, parcel stuck in transit",
    3: "Emma, bike past the return window",
    4: "Hugo, delivered yesterday",
    5: "Léa, no orders yet",
}

STEP_LABELS = {
    "search_knowledge_base": "Searching the help pages",
    "list_my_orders": "Looking at your orders",
    "get_order_details": "Checking order {order_number}",
    "check_return_eligibility": "Checking what can be returned on {order_number}",
    "create_return_request": "Preparing a return on {order_number}",
    "escalate_to_human": "Passing your case to the team",
}


def auth_headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}


def call_api(method: str, path: str, **kwargs) -> dict:
    response = httpx.request(
        method, f"{API_URL}{path}", headers=auth_headers(), timeout=30, **kwargs
    )
    response.raise_for_status()
    return response.json()


def stream_events(path: str, payload: dict):
    with httpx.stream(
        "POST", f"{API_URL}{path}", json=payload, headers=auth_headers(), timeout=120
    ) as response:
        response.raise_for_status()
        event = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                yield event, json.loads(line.removeprefix("data: "))


def log_in(customer_id: int) -> None:
    response = httpx.post(f"{API_URL}/auth/demo-login", json={"customer_id": customer_id})
    response.raise_for_status()
    st.session_state.token = response.json()["access_token"]
    st.session_state.customer_id = customer_id
    st.session_state.thread_id = call_api("POST", "/threads")["thread_id"]


def show_sources(sources: list[dict]) -> None:
    # These are the pages the search brought back, not necessarily the ones the
    # answer relies on, hence "checked". Several sections of a page show as one name.
    titles = dict.fromkeys(source["title"] for source in sources)
    if titles:
        st.caption("Pages checked: " + " · ".join(titles))


def describe(action: dict) -> str:
    args = action["args"]
    if action["name"] == "create_return_request":
        return (
            f"Open a return on order **{args['order_number']}** for "
            f"{', '.join(args['skus'])}, reason: *{args['reason']}*"
        )
    return f"{action['name']} {args}"


def run_agent(path: str, payload: dict) -> None:
    """Stream one run into an assistant bubble, then reload the page from the API."""
    with st.chat_message("assistant"):
        steps = None

        def tokens():
            nonlocal steps
            for event, data in stream_events(path, payload):
                if event == "token":
                    yield data["text"]
                elif event == "tool":
                    if steps is None:
                        steps = st.status("Working on it...")
                    label = STEP_LABELS.get(data["name"], data["name"])
                    steps.write(label.format(**data["args"]))
                elif event == "error":
                    st.error(data["detail"])

        st.write_stream(tokens())
        if steps is not None:
            steps.update(label="Done", state="complete")
    st.rerun()


st.set_page_config(page_title="Nomad Cycles support", page_icon="🚲")

with st.sidebar:
    st.header("Nomad Cycles")
    st.caption("Demo shop. Pick a customer to chat as them.")
    customer_id = st.radio("Logged in as", list(DEMO_CUSTOMERS), format_func=DEMO_CUSTOMERS.get)
    try:
        if st.session_state.get("customer_id") != customer_id:
            log_in(customer_id)
    except httpx.HTTPError:
        st.error(f"Can't reach the API at {API_URL}. Is it running?")
        st.stop()
    if st.button("New conversation"):
        st.session_state.thread_id = call_api("POST", "/threads")["thread_id"]

st.title("How can we help?")

thread_path = f"/threads/{st.session_state.thread_id}"
thread = call_api("GET", thread_path)
for message in thread["messages"]:
    with st.chat_message("user" if message["role"] == "customer" else "assistant"):
        st.markdown(message["content"])
        show_sources(message["sources"])

if thread["pending"]:
    with st.container(border=True):
        st.markdown("**Before I go ahead, can you confirm?**")
        for action in thread["pending"]:
            st.markdown(describe(action))
        confirm, cancel = st.columns(2)
        approved = confirm.button("Confirm", type="primary", use_container_width=True)
        declined = cancel.button("Cancel", use_container_width=True)
    if approved or declined:
        run_agent(f"{thread_path}/resume", {"approved": approved})

# While a confirmation is pending the API refuses new messages, so don't offer the box.
placeholder = "Confirm or cancel above first" if thread["pending"] else "Ask about an order..."
if prompt := st.chat_input(placeholder, disabled=bool(thread["pending"])):
    with st.chat_message("user"):
        st.markdown(prompt)
    run_agent(f"{thread_path}/messages", {"content": prompt})
