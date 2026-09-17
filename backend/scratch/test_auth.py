import asyncio
from app.brokers.kotak_neo import get_kotak_broker

async def main():
    broker = get_kotak_broker()
    print("Initial status:", broker.auth_status)
    ok = await broker.authenticate()
    print("Authentication result:", ok)
    print("Final status:", broker.auth_status)

if __name__ == "__main__":
    asyncio.run(main())
