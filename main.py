import asyncio
import logging
import sys

from db_manager import DatabaseManager
from ai_agent import AIAgent
from bot_client import BaleBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing Bale AI Bot...")
    
    # Initialize Core Components
    try:
        db = DatabaseManager()
        agent = AIAgent(db)
        bot = BaleBot(db, agent)
    except Exception as e:
        logger.critical(f"Initialization failed: {e}")
        return

    # Handle graceful shutdown
    # (In Python 3.8+ on Windows, add_signal_handler is not fully supported for all signals
    # without custom event loops, so we rely on KeyboardInterrupt around the run call)

    try:
        await bot.start()
    except asyncio.CancelledError:
        logger.info("Bot task cancelled.")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
    finally:
        await bot.stop()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        # Windows compatibility for asyncio if necessary
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, stopping...")
