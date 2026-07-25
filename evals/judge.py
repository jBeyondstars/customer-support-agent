from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from support_agent.config import get_settings
from support_agent.llm import get_chat_model

JUDGE_PROMPT = """\
You grade answers given by the support assistant of Nomad Cycles, an online bike shop.

You get the customer's message, the assistant's answer, everything its tools returned \
(extracts from the help pages and the customer's own order data) and a short note from \
whoever wrote the test about what a good answer contains.

correct:
- "yes": the answer gets the essentials of the note right.
- "partly": right overall but misses something important, or is confusing.
- "no": wrong, misleading, or doesn't answer the question.

grounded: true when every factual claim about the shop or the customer's orders \
(prices, delays, dates, rules, statuses, numbers) is backed by the tool outputs. \
Greetings, offers to help and general cycling common sense don't need backing, and \
neither do statements about what the assistant itself can or can't do (it can't cancel \
an order on its own, it can pass a request on to the team). \
false as soon as one such claim is invented or contradicts the tool outputs.

The answer may be in another language than the pages, that's expected: it should be \
in the customer's language."""


class Grade(BaseModel):
    correct: Literal["yes", "partly", "no"]
    grounded: bool
    explanation: str = Field(description="One or two sentences on what's right or wrong.")


def grade(message: str, answer: str, tool_outputs: list[str], reference: str) -> Grade:
    model = get_chat_model(get_settings().judge_model, streaming=False)
    evidence = "\n\n---\n\n".join(tool_outputs) or "(no tool was called)"
    return model.with_structured_output(Grade).invoke(
        [
            SystemMessage(JUDGE_PROMPT),
            HumanMessage(
                f"<customer>\n{message}\n</customer>\n\n"
                f"<answer>\n{answer}\n</answer>\n\n"
                f"<tool_outputs>\n{evidence}\n</tool_outputs>\n\n"
                f"<note>\n{reference}\n</note>"
            ),
        ]
    )
