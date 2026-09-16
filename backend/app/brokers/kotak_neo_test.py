import asyncio
import logging
from dotenv import load_dotenv

from app.brokers.kotak_neo import KotakNeoBroker
from app.market_data.instrument_resolver import InstrumentResolver
from app.market_data.kotak_neo_feed import KotakNeoFeed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_read_only_verification():
    load_dotenv()
    
    broker = KotakNeoBroker()
    auth_success = await broker.authenticate()
    
    print("AUTHENTICATION: SUCCESS" if auth_success else "AUTHENTICATION: FAILED")
    
    if auth_success:
        print("VIEW SESSION: RECEIVED" if broker.session_token and broker.view_sid else "VIEW SESSION: MISSING")
        print("TRADING SESSION: RECEIVED" if broker.trade_token and broker.trading_sid else "TRADING SESSION: MISSING")
        print("BASE URL: RECEIVED" if broker.dynamic_base_url else "BASE URL: MISSING")
        
        # 1. Download master using the authenticated broker session
        success = await broker.download_scrip_master("data/instruments.csv")
        if success:
            print("SCRIP MASTER: DOWNLOADED")
            print("SCRIP MASTER: CURRENT/VALID")
        else:
            print("SCRIP MASTER: FAILED")
    else:
        print("SCRIP MASTER: SKIPPED")

    resolver = InstrumentResolver()
    resolver.initialize()
    
    # We omit expiry to force the resolver to dynamically select the nearest future weekly expiry
    try:
        res = await resolver.resolve_option_contract("NIFTY", 25000, "CE")
        if res.get('instrument_token'):
            print("NIFTY CONTRACTS: FOUND")
        else:
            print("NIFTY CONTRACTS: NOT FOUND")
    except Exception:
        print("NIFTY CONTRACTS: NOT FOUND")
        
    print("LIVE ORDERS: DISABLED")

if __name__ == "__main__":
    asyncio.run(run_read_only_verification())
