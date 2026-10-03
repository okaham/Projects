"""Calls Claude to produce a reply. Phase 1: no memory, no tools - one message in, one reply out."""

import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120.0)

SYSTEM_PROMPT = """\
You are a personal assistant that your user texts over iMessage.
Write plain text only - iMessage does not render Markdown, so no **bold**, # headings, or tables.
Keep replies short, like a text message, unless the user asks for detail.
If you don't know something or can't do it, say so plainly instead of guessing."""


def get_reply(user_text: str) -> str:
    response = client.beta.messages.create(
        model=settings.claude_model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        # Effort controls how much Claude thinks before answering. "low" keeps texts fast and cheap.
        output_config={"effort": settings.claude_effort},
        # If Claude's safety filter wrongly declines a harmless message, the API retries it on a
        # fallback model inside the same call instead of returning nothing.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": user_text}],
    )

    logger.info(
        "Claude replied: stop_reason=%s input_tokens=%d output_tokens=%d",
        response.stop_reason,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    if response.stop_reason == "refusal":
        return "Sorry, I can't help with that one."

    # response.content is a list of blocks (thinking, text, ...). Keep only the text.
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or "(Claude returned an empty reply)"
