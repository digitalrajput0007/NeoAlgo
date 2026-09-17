import asyncio
from app.brokers.kotak_neo import KotakNeoBroker

async def main():
    broker = KotakNeoBroker()
    await broker.authenticate()
    from neo_api_client.neo_api import NeoAPI
    
    # Actually broker handles everything using `neo_api_client` under the hood in Phase 13A? Wait, no.
    client = NeoAPI(
        consumer_key=broker.consumer_key,
        environment='PROD',
    )
    # The client needs edit_token and edit_sid, but we can try search_scrip without it maybe?
    # No, search_scrip requires tokens. Let's provide them if available.
    try:
        client.bearer_token = broker.trade_token
        client.edit_token = broker.trade_token
        client.edit_sid = broker.trading_sid
        client.sid = broker.trading_sid
        
        res = client.search_scrip(exchange_segment="nse_cm", symbol="NIFTY 50")
        print("Search NSE CM NIFTY 50:", res)
    except Exception as e:
        print("Error NSE CM NIFTY 50:", e)
        
    try:
        res2 = client.search_scrip(exchange_segment="nse_cm", symbol="NIFTY")
        print("Search NSE CM NIFTY:", res2)
    except Exception as e:
        print("Error NSE CM NIFTY:", e)

    try:
        res3 = client.search_scrip(exchange_segment="bse_cm", symbol="SENSEX")
        print("Search BSE CM SENSEX:", res3)
    except Exception as e:
        print("Error BSE CM SENSEX:", e)

if __name__ == "__main__":
    asyncio.run(main())
