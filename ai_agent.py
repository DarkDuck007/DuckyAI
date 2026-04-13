import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, messages_from_dict
from langchain_google_genai import ChatGoogleGenerativeAI

from config import config
from db_manager import DatabaseManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful and intelligent AI assistant powered by Gemini. "
    "You are chatting with a user on Bale Messenger. Be concise and friendly."
)

SUMMARY_SYSTEM_PROMPT = (
    "You maintain compact long-term memory for an AI chat assistant. "
    "Update the existing memory with the new transcript. Keep stable user facts, "
    "preferences, goals, decisions, names, constraints, and unresolved tasks. "
    "Remove small talk, duplicate details, and outdated information unless it matters. "
    "Write a dense summary that is useful for future replies."
)


@dataclass(frozen=True)
class ContextSettings:
    recent_message_limit: int = getattr(config, "AI_RECENT_MESSAGE_LIMIT", 12)
    summary_trigger_messages: int = getattr(config, "AI_SUMMARY_TRIGGER_MESSAGES", 28)
    summary_batch_message_limit: int = getattr(config, "AI_SUMMARY_BATCH_MESSAGE_LIMIT", 40)
    max_summary_chars: int = getattr(config, "AI_MAX_SUMMARY_CHARS", 3000)

    def __post_init__(self):
        recent_message_limit = max(2, self.recent_message_limit)
        summary_trigger_messages = max(recent_message_limit + 2, self.summary_trigger_messages)
        summary_batch_message_limit = max(2, self.summary_batch_message_limit)
        max_summary_chars = max(500, self.max_summary_chars)

        object.__setattr__(self, "recent_message_limit", recent_message_limit)
        object.__setattr__(self, "summary_trigger_messages", summary_trigger_messages)
        object.__setattr__(self, "summary_batch_message_limit", summary_batch_message_limit)
        object.__setattr__(self, "max_summary_chars", max_summary_chars)


class AIAgent:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.context_settings = ContextSettings()
        
        # Initialize Google GenAI chat model
        # Disabling streaming to prevent running into Bale Bot API rate limits (1 edit/sec)
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=config.GEMINI_API_KEY,
            temperature=0.7,
            streaming=False
        )

    def _get_session_history(self, session_id: str):
        # We use a direct connection string to the storage database
        connection_string = f"sqlite:///{self.db_manager.storage_db}"
        
        return SQLChatMessageHistory(
            session_id=session_id,
            connection_string=connection_string,
            table_name="message_store"
        )

    def _deserialize_rows(self, rows: Iterable[Tuple[int, str]]) -> List[Tuple[int, BaseMessage]]:
        messages: List[Tuple[int, BaseMessage]] = []
        for message_id, raw_message in rows:
            try:
                messages.append((message_id, messages_from_dict([json.loads(raw_message)])[0]))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Skipping unreadable chat history row %s: %s", message_id, exc)
        return messages

    def _message_label(self, message: BaseMessage) -> str:
        if isinstance(message, HumanMessage):
            return "User"
        if isinstance(message, AIMessage):
            return "Assistant"
        if isinstance(message, SystemMessage):
            return "System"
        return message.type.title()

    def _message_text(self, message: BaseMessage) -> str:
        content = message.content
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    def _format_transcript(self, messages: Sequence[BaseMessage]) -> str:
        return "\n".join(
            f"{self._message_label(message)}: {self._message_text(message)}"
            for message in messages
        )

    def _summarize_messages(self, current_summary: str, messages: Sequence[BaseMessage]) -> str:
        """Compacts a batch of older messages into the persisted session summary."""
        transcript = self._format_transcript(messages)
        summary_prompt = (
            f"Maximum summary length: {self.context_settings.max_summary_chars} characters.\n\n"
            f"Existing memory:\n{current_summary or '(none)'}\n\n"
            f"New transcript to fold into memory:\n{transcript}\n\n"
            "Updated memory:"
        )
        response = self.llm.invoke([
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=summary_prompt),
        ])
        summary = self._message_text(response).strip()
        return summary or current_summary

    def _compact_history_if_needed(self, session_id: str) -> Tuple[str, int]:
        """
        Summarize older unsummarized turns so prompt context stays bounded.

        The raw message rows remain in storage for audit/export, but only the
        persisted summary plus recent messages are sent to Gemini.
        """
        summary, summarized_message_id = self.db_manager.get_session_summary(session_id)
        rows = self.db_manager.get_message_rows_after(session_id, summarized_message_id)

        if len(rows) <= self.context_settings.summary_trigger_messages:
            return summary, summarized_message_id

        rows_to_summarize = rows[:-self.context_settings.recent_message_limit]
        if not rows_to_summarize:
            return summary, summarized_message_id

        for index in range(0, len(rows_to_summarize), self.context_settings.summary_batch_message_limit):
            batch_rows = rows_to_summarize[index:index + self.context_settings.summary_batch_message_limit]
            batch_messages = [message for _, message in self._deserialize_rows(batch_rows)]
            if not batch_messages:
                continue

            summary = self._summarize_messages(summary, batch_messages)
            summarized_message_id = batch_rows[-1][0]
            self.db_manager.upsert_session_summary(session_id, summary, summarized_message_id)

        return summary, summarized_message_id

    def _build_messages(self, session_id: str, user_input: str) -> List[BaseMessage]:
        try:
            summary, summarized_message_id = self._compact_history_if_needed(session_id)
        except Exception as exc:
            logger.warning("Unable to compact chat history for session %s: %s", session_id, exc)
            summary, summarized_message_id = self.db_manager.get_session_summary(session_id)

        recent_rows = self.db_manager.get_recent_message_rows_after(
            session_id,
            summarized_message_id,
            self.context_settings.recent_message_limit
        )
        recent_messages = [message for _, message in self._deserialize_rows(recent_rows)]

        messages: List[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
        if summary:
            messages.append(SystemMessage(
                content=(
                    "Long-term conversation memory. Use it only when relevant, "
                    "and rely on recent messages for immediate context:\n"
                    f"{summary}"
                )
            ))
        messages.extend(recent_messages)
        messages.append(HumanMessage(content=user_input))
        return messages

    async def chat(self, session_id: str, message_text: str) -> str:
        """Invokes the AI model for the given session ID and human message."""
        history = self._get_session_history(session_id)

        def invoke_and_store() -> str:
            messages = self._build_messages(session_id, message_text)
            response = self.llm.invoke(messages)
            response_text = self._message_text(response)

            history.add_user_message(message_text)
            history.add_ai_message(response_text)
            self._compact_history_if_needed(session_id)
            return response_text

        return await asyncio.to_thread(invoke_and_store)
