import asyncio
from app.brokers.kotak_neo import get_kotak_broker
from neo_api_client import NeoAPI
import json

async def main():
    broker = get_kotak_broker()
    # It might not be authenticated, we need to call authenticate
    connected = await broker.authenticate()
    if not connected:
        print("Failed to connect.")
        return
        
    print("Connected. Initializing NeoAPI...")
    
    try:
        client = NeoAPI(consumer_key=broker.consumer_key, access_token=broker.session_token)
        # In v3.x, some auth logic might require overriding configuration
        client.configuration.edit_token = broker.trade_token
        client.configuration.edit_sid = broker.trading_sid
        # data_center could be the serverId
        client.configuration.serverId = broker.data_center or "1"
        
        # Test limits
        limits_res = client.limits()
        print("LIMITS RESPONSE:")
        print(json.dumps(limits_res, indent=2))
        
    except Exception as e:
        print(f"Error calling limits: {e}")

if __name__ == "__main__":
    asyncio.run(main())
