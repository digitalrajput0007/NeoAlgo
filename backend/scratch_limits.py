import asyncio
from app.brokers.kotak_neo import get_kotak_broker
import json

async def main():
    broker = get_kotak_broker()
    # Ensure it's connected first. For test, we might just try to call it if it's connected
    if hasattr(broker, 'client') and broker.client:
        try:
            res = broker.client.limits()
            print("LIMITS RESPONSE:")
            print(json.dumps(res, indent=2))
        except Exception as e:
            print(f"Error calling limits: {e}")
    else:
        print("No client on broker.")

if __name__ == "__main__":
    asyncio.run(main())
