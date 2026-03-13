import asyncio
import httpx
import logging
from typing import Optional

from config import config
from db_manager import DatabaseManager
from ai_agent import AIAgent

logger = logging.getLogger(__name__)

class BaleBot:
    def __init__(self, db_manager: DatabaseManager, ai_agent: AIAgent):
        self.token = config.BALE_BOT_TOKEN
        self.base_url = f"https://tapi.bale.ai/bot{self.token}"
        self.db = db_manager
        self.agent = ai_agent
        self.offset = 0
        self.client: Optional[httpx.AsyncClient] = None
        self.is_running = False

    async def start(self):
        """Starts the bot polling loop."""
        self.client = httpx.AsyncClient(timeout=60.0)
        self.is_running = True
        logger.info("Bot started polling...")
        
        while self.is_running:
            try:
                updates = await self.get_updates()
                if updates:
                    for update in updates:
                        await self.handle_update(update)
                        self.offset = update["update_id"] + 1
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(5)  # Backoff on error

    async def stop(self):
        """Stops the bot."""
        self.is_running = False
        if self.client:
            await self.client.aclose()

    async def get_updates(self, timeout: int = 30) -> list:
        """Fetches updates from the API."""
        url = f"{self.base_url}/getUpdates"
        payload = {
            "offset": self.offset,
            "timeout": timeout
        }
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if data.get("ok"):
                return data.get("result", [])
            else:
                logger.warning(f"Failed to get updates: {data.get('description')}")
        except httpx.ReadTimeout:
            pass  # Expected during long polling
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during getUpdates: {e}")
        return []

    async def send_message(self, chat_id: int, text: str):
        """Sends a text message to a specific chat."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": text
        }
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Error sending message to {chat_id}: {e}")

    async def handle_update(self, update: dict):
        """Processes a single update."""
        if "message" not in update:
            return  # Only handle messages
            
        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        
        if not text:
            return

        # Handle commands
        if text.startswith("/"):
            await self.handle_command(chat_id, text)
            return

        # Ensure user and default session exist
        session_id = self.db.get_or_create_user(chat_id)
        active_session = self.db.get_active_session(chat_id)
        
        if not active_session:
            # Fallback if somehow deleted
            active_session = self.db.create_new_session(chat_id)
            
        # Send a typing indicator or 'Thinking...' placeholder
        # To avoid rate limits, we'll just send "Thinking..." if the response might be slow,
        # but the prompt requested no streaming to avoid edits. We'll simply wait for Gemini
        # and send the final result to avoid HTTP 429 errors from editing.
        
        try:
            # Get AI response
            response_text = await self.agent.chat(active_session, text)
            await self.send_message(chat_id, response_text)
        except Exception as e:
            logger.error(f"AI Agent error: {e}")
            await self.send_message(chat_id, "Sorry, I encountered an error processing your request.")

    async def handle_command(self, chat_id: int, command_text: str):
        """Processes bot commands."""
        parts = command_text.split()
        cmd = parts[0].lower()

        if cmd == "/start":
            self.db.get_or_create_user(chat_id)
            welcome_msg = (
                "Hello! I am your AI assistant powered by Gemini. \n\n"
                "Commands:\n"
                "/newchat [name] - Start a new conversation context\n"
                "/chats - List your chat sessions\n"
                "/switch <id> - Switch to an existing chat context\n"
                "/deletechat <id> - Delete a specific chat context"
            )
            await self.send_message(chat_id, welcome_msg)

        elif cmd == "/newchat":
            name = " ".join(parts[1:]) if len(parts) > 1 else None
            session_id = self.db.create_new_session(chat_id, name)
            await self.send_message(chat_id, f"Created and switched to new chat: {name or 'Session'}\nID: `{session_id[:8]}`...")

        elif cmd == "/chats":
            sessions = self.db.list_sessions(chat_id)
            active_session = self.db.get_active_session(chat_id)
            
            if not sessions:
                await self.send_message(chat_id, "You have no active chat sessions.")
                return
                
            msg = "Your chat sessions:\n"
            for sid, name in sessions:
                active_marker = " (Active)" if sid == active_session else ""
                msg += f"• `{sid[:8]}` - {name}{active_marker}\n"
            
            await self.send_message(chat_id, msg)

        elif cmd == "/switch":
            if len(parts) < 2:
                await self.send_message(chat_id, "Usage: /switch <id>")
                return
            
            target_prefix = parts[1]
            sessions = self.db.list_sessions(chat_id)
            
            for sid, name in sessions:
                if sid.startswith(target_prefix):
                    self.db.set_active_session(chat_id, sid)
                    await self.send_message(chat_id, f"Switched to chat: {name}")
                    return
            
            await self.send_message(chat_id, "Chat session not found.")

        elif cmd == "/deletechat":
            if len(parts) < 2:
                await self.send_message(chat_id, "Usage: /deletechat <id>")
                return
                
            target_prefix = parts[1]
            sessions = self.db.list_sessions(chat_id)
            
            for sid, name in sessions:
                if sid.startswith(target_prefix):
                    active_session = self.db.get_active_session(chat_id)
                    self.db.delete_session(sid)
                    
                    if sid == active_session:
                        # Reassign to another session if possible
                        remaining = self.db.list_sessions(chat_id)
                        if remaining:
                            self.db.set_active_session(chat_id, remaining[0][0])
                            await self.send_message(chat_id, f"Deleted chat '{name}'. Auto-switched to '{remaining[0][1]}'.")
                        else:
                            # Create a brand new one
                            self.db.create_new_session(chat_id, "Default Session")
                            await self.send_message(chat_id, f"Deleted chat '{name}'. Created a new default session.")
                    else:
                        await self.send_message(chat_id, f"Deleted chat '{name}'.")
                    return
                    
            await self.send_message(chat_id, "Chat session not found.")
        else:
            await self.send_message(chat_id, "Unknown command.")
