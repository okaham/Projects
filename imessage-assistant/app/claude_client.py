"""Calls Claude to produce a reply, running any tools Claude asks for along the way."""

import logging
from datetime import datetime

import anthropic

from app.config import settings
from app.tools import enabled_tools, run_tool

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120.0)

SYSTEM_PROMPT = """\
You are a personal assistant that your user texts over iMessage.
Write plain text only - iMessage does not render Markdown, so no **bold**, # headings, or tables.
Keep replies short, like a text message, unless the user asks for detail.
If you don't know something or can't do it, say so plainly instead of guessing.
If a tool returns an error, tell the user what went wrong in one line, including any fix it mentions."""

# Safety limit: at most this many rounds of tool calls per text, so a confused model can't loop forever.
MAX_TOOL_ROUNDS = 5


def get_reply(user_text: str, history: list[dict] | None = None) -> str:
    """history: earlier messages in this chat, oldest first, e.g.
    [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hey!"}]
    Pass None or [] to answer with no memory.

    The tool loop: Claude either answers (done) or asks to use tools (stop_reason "tool_use").
    In the second case we run the tools, add the results to the conversation, and ask again.
    """
    messages = list(history or []) + [{"role": "user", "content": user_text}]
    tools = enabled_tools()

    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = _call_claude(messages, tools, history_len=len(history or []))

        if response.stop_reason == "refusal":
            return "Sorry, I can't help with that one."
        if response.stop_reason != "tool_use":
            # response.content is a list of blocks (thinking, text, ...). Keep only the text.
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return text or "(Claude returned an empty reply)"

        # Claude wants tools. Send back its whole response unchanged (it can contain thinking
        # blocks the API expects to see again), then one message with ALL the tool results.
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": _run_tool_calls(response.content)})

    logger.warning("Gave up after %d tool rounds", MAX_TOOL_ROUNDS)
    return "Sorry, that took too many steps. Try asking more specifically."


def _call_claude(messages: list, tools: list[dict], history_len: int):
    now = datetime.now().astimezone()  # Mac's local time, with time zone
    request = dict(
        model=settings.claude_model,
        max_tokens=16000,
        # The current time goes in the system prompt so "today" and "tomorrow" mean something.
        system=f"{SYSTEM_PROMPT}\n\nCurrent local date and time: {now:%A, %B %d, %Y, %I:%M %p %Z}.",
        # Effort controls how much Claude thinks before answering. "low" keeps texts fast and cheap.
        output_config={"effort": settings.claude_effort},
        # If Claude's safety filter wrongly declines a harmless message, the API retries it on a
        # fallback model inside the same call instead of returning nothing.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=messages,
    )
    if tools:  # only send the parameter when there's something in it
        request["tools"] = tools

    response = client.beta.messages.create(**request)
    logger.info(
        "Claude replied: history=%d msgs stop_reason=%s input_tokens=%d output_tokens=%d",
        history_len,
        response.stop_reason,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    return response


def _run_tool_calls(content: list) -> list[dict]:
    results = []
    for block in content:
        if block.type == "tool_use":
            text, is_error = run_tool(block.name, block.input)
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error}
            )
    return results
