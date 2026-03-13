import asyncio
from ai_agent import AIAgent
from db_manager import DatabaseManager

async def test():
    db = DatabaseManager('main.db', 'storage.db')
    agent = AIAgent(db)
    try:
        res = await agent.chat('test_session', 'Hello!')
        print(f"Response: {res}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test())
