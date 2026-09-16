import asyncio
import logging
import sys
import os
sys.path.append(r"C:\Users\sbiet\.gemini\antigravity-ide\brain\e16155c8-02b0-495c-9a87-a8d5b84739a9\scratch\kotak_neo")
from neo_api_client import NeoAPI

logging.basicConfig(level=logging.DEBUG)

def main():
    from app.config import settings
    # Initialize exactly as scrip_master.md says
    client = NeoAPI(environment="prod", consumer_key=settings.kotak_neo_consumer_key)
    try:
        res = client.scrip_master()
        print(res)
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    main()
