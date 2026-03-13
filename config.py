import os
from dotenv import load_dotenv

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

        if not self.BALE_BOT_TOKEN:
            raise ValueError("BALE_BOT_TOKEN environment variable is missing.")
        if not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is missing.")

config = Config()
