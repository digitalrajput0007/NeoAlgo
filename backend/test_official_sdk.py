from neo_api_client import NeoAPI
from app.config import settings
import os

def main():
    consumer_key = settings.kotak_neo_consumer_key
    print(f"Testing official SDK scrip_master with consumer_key {consumer_key[:10]}...")
    
    try:
        client = NeoAPI(
            consumer_key=consumer_key,
            environment="prod"
        )
        result = client.scrip_master(exchange_segment="nse_fo")
        print("Type:", type(result))
        print("Result:", result)
    except Exception as e:
        print("Exception:", e)

if __name__ == "__main__":
    main()
