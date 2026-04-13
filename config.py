import os
from dotenv import load_dotenv

def get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

def load_config():
    # Load .env file with override priority: System ENV > .env file
    env_path = os.getenv("BALE_BOT_ENV_PATH", "EnvironmentVariables.env")
    load_dotenv(dotenv_path=env_path, override=True)

class Config:
    def __init__(self):
        load_config()
        self.BALE_BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
        self.BALE_BOT_USERNAME = os.getenv("BALE_BOT_Username", "@DuckyAIBot")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        
        # Determine database paths based on the running environment's current working directory
        self.MAIN_DB = os.getenv("MAIN_DB_PATH", "main.db")
        self.STORAGE_DB = os.getenv("STORAGE_DB_PATH", "storage.db")

        # Context compaction settings. Older messages are summarized, while this
        # many recent messages remain verbatim for immediate conversational flow.
        self.AI_RECENT_MESSAGE_LIMIT = get_int_env("AI_RECENT_MESSAGE_LIMIT", 12)
        self.AI_SUMMARY_TRIGGER_MESSAGES = get_int_env("AI_SUMMARY_TRIGGER_MESSAGES", 28)
        self.AI_SUMMARY_BATCH_MESSAGE_LIMIT = get_int_env("AI_SUMMARY_BATCH_MESSAGE_LIMIT", 40)
        self.AI_MAX_SUMMARY_CHARS = get_int_env("AI_MAX_SUMMARY_CHARS", 3000)

        if not self.BALE_BOT_TOKEN:
            raise ValueError("BALE_BOT_TOKEN environment variable is missing.")
        if not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is missing.")

config = Config()
