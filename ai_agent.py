from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

import asyncio

from config import config
from db_manager import DatabaseManager

class AIAgent:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
        # Initialize Google GenAI chat model
        # Disabling streaming to prevent running into Bale Bot API rate limits (1 edit/sec)
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=config.GEMINI_API_KEY,
            temperature=0.7,
            streaming=False
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful and intelligent AI assistant powered by Gemini. You are chatting with a user on Bale Messenger. Be concise and friendly."),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])
        
        self.chain = self.prompt | self.llm

    def _get_session_history(self, session_id: str):
        # We use a direct connection string to the storage database
        connection_string = f"sqlite:///{self.db_manager.storage_db}"
        
        return SQLChatMessageHistory(
            session_id=session_id,
            connection_string=connection_string,
            table_name="message_store"
        )

    def get_runnable(self):
        """Returns the Runnable wrapping the LLM chain and memory."""
        return RunnableWithMessageHistory(
            self.chain,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="history"
        )

    async def chat(self, session_id: str, message_text: str) -> str:
        """Invokes the AI model for the given session ID and human message."""
        runnable = self.get_runnable()
        config_dict = {"configurable": {"session_id": session_id}}
        
        # Asynchronously invoke the LLM chain using sync invoke in an executor thread
        response = await asyncio.to_thread(
            runnable.invoke,
            {"input": message_text},
            config=config_dict
        )
        return response.content
