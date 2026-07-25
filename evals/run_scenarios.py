"""Run the agent on scripted customer messages and check what it did.

Two kinds of checks. The deterministic ones don't need an LLM: which tools were
called, whether the guard blocked the message, whether the run stopped to ask
for confirmation, a few facts the answer must contain, and that nothing
belonging to another customer (order number, tracking number, email) shows up
in the answer or in any tool output.

Then a stronger model reads each answer next to the tool outputs and a reference
note, and says whether it's correct and whether every fact in it is backed by
the tools (judge.py). Skip that part with --no-judge.

Expects a freshly seeded database: python scripts/seed_db.py
"""

import argparse
import json
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg
from judge import Grade, grade
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from support_agent.agent.graph import build_graph
from support_agent.agent.state import Context
from support_agent.config import get_settings

HERE = Path(__file__).parent


@dataclass
class Run:
    scenario: dict
    seconds: float
    answer: str = ""
    tools: list[str] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)
    blocked: bool = False
    pending: list[dict] = field(default_factory=list)
    tokens: int = 0
    failures: list[str] = field(default_factory=list)
    grade: Grade | None = None

    @property
    def gradable(self) -> bool:
        # Guard refusals and runs paused for confirmation have no answer to grade.
        return bool(self.answer) and not self.blocked and "reference" in self.scenario


def run_scenario(graph, scenario: dict) -> Run:
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    start = time.perf_counter()
    result = graph.invoke(
        {"messages": [HumanMessage(scenario["message"])]},
        config,
        context=Context(customer_id=scenario["customer"]),
    )
    run = Run(scenario, seconds=time.perf_counter() - start)

    for message in result["messages"]:
        if isinstance(message, AIMessage):
            run.tools += [call["name"] for call in message.tool_calls]
            run.tokens += (message.usage_metadata or {}).get("total_tokens", 0)
            run.blocked = message.name == "guard"
            if message.text:
                run.answer = message.text
        elif isinstance(message, ToolMessage):
            run.tool_outputs.append(message.text)
    run.pending = [action for pause in result.get("__interrupt__", []) for action in pause.value]
    return run


def grade_run(run: Run) -> Grade:
    return grade(run.scenario["message"], run.answer, run.tool_outputs, run.scenario["reference"])


def check(run: Run, others: set[str]) -> list[str]:
    expect = run.scenario["expect"]
    failures = []

    if "blocked" in expect and run.blocked != expect["blocked"]:
        failures.append("not blocked by the guard" if expect["blocked"] else "blocked by the guard")
    if missing := [t for t in expect.get("tools", []) if t not in run.tools]:
        failures.append(f"didn't call {', '.join(missing)}")
    if expect.get("tools_any") and not set(expect["tools_any"]) & set(run.tools):
        failures.append(f"called none of {', '.join(expect['tools_any'])}")
    if called := [t for t in expect.get("no_tools", []) if t in run.tools]:
        failures.append(f"called {', '.join(called)}")

    if "paused" in expect and bool(run.pending) != expect["paused"]:
        failures.append("didn't ask for confirmation" if expect["paused"] else "asked to confirm")
    elif run.pending and "skus" in expect:
        skus = sorted(run.pending[0]["args"].get("skus", []))
        if skus != sorted(expect["skus"]):
            failures.append(f"wanted to return {skus}, expected {sorted(expect['skus'])}")

    answer = run.answer.lower()
    if absent := [fact for fact in expect.get("include", []) if fact.lower() not in answer]:
        failures.append(f"answer doesn't mention {', '.join(absent)}")

    # Echoing an order number the customer typed themselves isn't a leak.
    suspects = {i for i in others if i not in run.scenario["message"]}
    seen = [run.answer, *run.tool_outputs]
    if leaked := sorted(i for i in suspects if any(i in text for text in seen)):
        failures.append(f"LEAK: {', '.join(leaked[:3])}")
    return failures


def identifiers_by_customer(conn: psycopg.Connection) -> dict[int, set[str]]:
    rows = conn.execute(
        """
        select c.id, c.email, o.number, s.tracking_number
        from customers c
        left join orders o on o.customer_id = c.id
        left join shipments s on s.order_id = o.id
        """
    ).fetchall()
    owned: dict[int, set[str]] = {}
    for customer_id, *values in rows:
        owned.setdefault(customer_id, set()).update(v for v in values if v)
    return owned


def main() -> None:
    parser = argparse.ArgumentParser()
    # The same message doesn't always get the same behaviour, one run per
    # scenario would make the numbers depend on luck.
    parser.add_argument("--repeat", type=int, default=3, help="runs per scenario")
    parser.add_argument("--no-judge", action="store_true", help="deterministic checks only")
    parser.add_argument(
        "--only", help="comma-separated scenario ids; prints the report without saving it"
    )
    args = parser.parse_args()

    lines = (HERE / "datasets" / "scenarios.jsonl").read_text(encoding="utf-8").splitlines()
    scenarios = [json.loads(line) for line in lines if line.strip()]
    if args.only:
        wanted = args.only.split(",")
        scenarios = [s for s in scenarios if s["id"] in wanted]

    with psycopg.connect(get_settings().database_url) as conn:
        latest = conn.execute("select max(placed_at) from orders").fetchone()[0]
        owned = identifiers_by_customer(conn)
    if datetime.now(UTC) - latest > timedelta(days=7):
        print("Warning: the seed is over a week old, return windows have moved. Reseed first.\n")
    everything = set().union(*owned.values())

    graph = build_graph(InMemorySaver())
    jobs = [scenario for scenario in scenarios for _ in range(args.repeat)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(lambda s: run_scenario(graph, s), jobs))
        for run in runs:
            run.failures = check(run, everything - owned[run.scenario["customer"]])
        if not args.no_judge:
            to_grade = [run for run in runs if run.gradable]
            for run, result in zip(to_grade, pool.map(grade_run, to_grade), strict=True):
                run.grade = result

    report = render(runs, args.repeat)
    if not args.only:
        (HERE / "reports").mkdir(exist_ok=True)
        (HERE / "reports" / "scenarios.md").write_text(report, encoding="utf-8", newline="\n")
    print(report)


def render(runs: list[Run], repeat: int) -> str:
    by_scenario: dict[str, list[Run]] = {}
    for run in runs:
        by_scenario.setdefault(run.scenario["id"], []).append(run)

    totals, passed = Counter(), Counter()
    for run in runs:
        totals[run.scenario["category"]] += 1
        passed[run.scenario["category"]] += not run.failures
    always = sum(all(not r.failures for r in group) for group in by_scenario.values())
    leaks = sum(any(f.startswith("LEAK") for f in run.failures) for run in runs)

    lines = [
        f"# Agent scenarios, {date.today()}",
        "",
        f"{len(by_scenario)} scenarios, {repeat} runs each. "
        f"{sum(passed.values())}/{len(runs)} runs pass, {always} scenarios pass every time. "
        f"Leaks: {leaks}.",
        "",
        f"Average {sum(r.seconds for r in runs) / len(runs):.1f}s and "
        f"{sum(r.tokens for r in runs) / len(runs):,.0f} agent tokens per run "
        "(the guard's call isn't counted).",
        "",
        "| category | runs passed |",
        "|---|---|",
        *[f"| {category} | {passed[category]}/{total} |" for category, total in totals.items()],
        "",
    ]

    graded = [run for run in runs if run.grade]
    if graded:
        verdicts = Counter(run.grade.correct for run in graded)
        grounded = sum(run.grade.grounded for run in graded)
        lines += [
            f"Judge ({get_settings().judge_model}) on the {len(graded)} runs that produced "
            f"an answer: correct {verdicts['yes']}, partly {verdicts['partly']}, "
            f"wrong {verdicts['no']}. Grounded in the tool outputs: {grounded}/{len(graded)}.",
            "",
        ]

    lines += [
        "| scenario | checks passed | judge: correct / grounded | what went wrong |",
        "|---|---|---|---|",
    ]
    for scenario_id, group in by_scenario.items():
        ok = sum(not r.failures for r in group)
        problems = "; ".join(dict.fromkeys(f for r in group for f in r.failures)) or "-"
        judged = [r.grade for r in group if r.grade]
        judge = (
            f"{sum(g.correct == 'yes' for g in judged)}/{len(judged)}"
            f" / {sum(g.grounded for g in judged)}/{len(judged)}"
            if judged
            else "-"
        )
        lines.append(f"| {scenario_id} | {ok}/{len(group)} | {judge} | {problems} |")

    notes = [
        f"- **{run.scenario['id']}** ({run.grade.correct}, "
        f"{'grounded' if run.grade.grounded else 'NOT grounded'}): {run.grade.explanation}"
        for run in graded
        if run.grade.correct != "yes" or not run.grade.grounded
    ]
    if notes:
        lines += ["", "## Judge notes", "", *notes]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
