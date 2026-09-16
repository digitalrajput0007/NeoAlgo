from typing import List, Dict, Any
from decimal import Decimal
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.telegram.parser import parse_message
from app.trading.trade_manager import TradeManager
from app.brokers.paper import PaperBroker
from app.database.models import TelegramMessage

logger = logging.getLogger(__name__)

class ReplayEngine:
    def __init__(self, db: AsyncSession, broker: PaperBroker, user_id: int, broker_account_id: int):
        self.db = db
        self.broker = broker
        self.broker.simulator_mode = True
        self.manager = TradeManager(db, broker)
        self.user_id = user_id
        self.broker_account_id = broker_account_id

    async def play_events(self, events: List[Dict[str, Any]]):
        """
        Process a list of deterministic events sequentially.
        """
        for event in events:
            event_type = event.get("type")
            
            if event_type == "telegram":
                await self._process_telegram_event(event)
            elif event_type == "price":
                await self._process_price_event(event)
            else:
                logger.warning(f"Unknown event type in replay: {event_type}")

    async def _process_telegram_event(self, event: Dict[str, Any]):
        msg_id = event["message_id"]
        channel_id = event["channel_id"]
        text = event["message"]
        
        logger.info(f"[REPLAY] Processing Telegram Message {msg_id}: {text[:30]}...")
        
        parsed = parse_message(text)
        
        # Explicit Duplicate Check
        is_duplicate = await self.manager.is_duplicate_message(msg_id, channel_id)
        if is_duplicate:
            logger.info(f"DUPLICATE_MESSAGE_IGNORED: {msg_id}")
            await self.manager._log_audit(self.user_id, None, "DUPLICATE_MESSAGE_IGNORED", {"message_id": msg_id})
            return
            
        # Store message to avoid future duplicates
        await self.manager.record_telegram_message(msg_id, channel_id, text, parsed)

        if parsed.parsed_successfully and parsed.signal:
            # It's a new signal
            trade = await self.manager.process_new_signal(
                self.user_id, self.broker_account_id, parsed.signal, message_id=msg_id
            )
            logger.info(f"[REPLAY] Trade processed. Status: {trade.status}")
        else:
            # Check for Exit / SL Hit / Partial Profit
            await self.manager.execute_manual_exit(
                parsed.message_type, channel_id, event.get("timestamp", None)
            )

    async def _process_price_event(self, event: Dict[str, Any]):
        instrument = event["instrument"]
        price = float(event["price"]) # Broker and internal logic still use float for LTP flow
        
        logger.info(f"[REPLAY] Injecting Price: {instrument} @ {price}")
        
        self.broker.inject_price(instrument, price)
        await self.manager.evaluate_market_prices(instrument, price)
