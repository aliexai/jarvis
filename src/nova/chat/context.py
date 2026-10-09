"""Conversation context management.

Sends a recent window verbatim and compresses everything older into a rolling
summary, so long conversations stay cheap. Summaries are persisted, so a restart
does not re-summarize.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nova.logging_setup import get_logger
from nova.memory.chats import ChatStore, StoredMessage
from nova.providers.base import LLMProvider, LLMRequest, Message, Usage
from nova.providers.errors import ProviderError

SUMMARY_SYSTEM = (
    "You compress conversations. Preserve decisions, facts, names, preferences and any "
    "unfinished work. Drop pleasantries. Reply with the summary only."
)


@dataclass
class Context:
    messages: list[Message]
    summary: str | None = None
    summarized: bool = False
    summary_usage: Usage | None = field(default=None)


class ContextBuilder:
    def __init__(
        self,
        store: ChatStore,
        provider: LLMProvider,
        *,
        summary_model: str,
        window_messages: int = 12,
        summarize_after: int = 20,
    ) -> None:
        self._store = store
        self._provider = provider
        self._summary_model = summary_model
        self._window = max(2, window_messages)
        self._summarize_after = max(self._window + 2, summarize_after)
        self._log = get_logger("chat.context")

    async def build(self, conversation_id: str) -> Context:
        recent = [
            message
            for message in self._store.recent_messages(conversation_id, self._window)
            if message.content
        ]
        summary, upto = self._store.get_summary(conversation_id)
        summarized = False
        summary_usage: Usage | None = None

        total = self._store.count_messages(conversation_id)
        if total > self._summarize_after and recent:
            older = self._store.messages_between(
                conversation_id, after_id=upto, before_id=recent[0].id
            )
            if len(older) >= max(4, self._window // 2):
                new_summary, summary_usage = await self._summarize(summary, older)
                if new_summary:
                    summary = new_summary
                    self._store.set_summary(conversation_id, new_summary, older[-1].id)
                    summarized = True

        messages = [
            Message(role="user" if message.role == "user" else "model", text=message.content)
            for message in recent
            if message.role in ("user", "model")
        ]
        return Context(
            messages=messages, summary=summary, summarized=summarized, summary_usage=summary_usage
        )

    async def _summarize(
        self, existing: str | None, older: list[StoredMessage]
    ) -> tuple[str | None, Usage | None]:
        transcript = "\n".join(
            f"{'User' if m.role == 'user' else 'NOVA'}: {m.content}" for m in older
        )[:4000]
        sections = []
        if existing:
            sections.append(f"Existing summary:\n{existing}")
        sections.append(f"New turns:\n{transcript}")
        sections.append("Write the updated summary in under 150 words.")
        prompt = "\n\n".join(sections)

        try:
            completion = await self._provider.complete(
                LLMRequest(
                    model=self._summary_model,
                    messages=[Message("user", prompt)],
                    system_instruction=SUMMARY_SYSTEM,
                    temperature=0.2,
                    max_output_tokens=256,
                )
            )
        except ProviderError as exc:
            self._log.warning("summarisation skipped: %s", exc.kind)
            return existing, None
        except Exception:
            self._log.exception("summarisation failed unexpectedly")
            return existing, None

        text = completion.text.strip()
        return (text[:2000] or existing), completion.usage
