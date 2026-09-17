import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union

from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User
from telethon.errors import SessionPasswordNeededError

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import TelegramChannel, TelegramMessage, Trade, TradeState, Signal
from app.telegram.parser import parse_message
from app.telegram.models import TelegramMessageType, ParseResult
from app.trading.trade_manager import TradeManager
from app.brokers.paper import PaperBroker
from app.market_data.instrument_resolver import InstrumentResolver
from app.services.market_data_service import market_data_service
from app.utils.timezone import to_utc_iso

logger = logging.getLogger(__name__)

def normalize_telegram_id(cid: Any) -> str:
    """Normalizes Telegram chat/channel IDs by stripping -100 prefix and negative signs."""
    s = str(cid).strip()
    if s.startswith("-100"):
        return s[4:]
    if s.startswith("-"):
        return s[1:]
    return s

class TelegramListenerService:
    _instance = None

    def __init__(self):
        self.is_running: bool = False
        self.client: Optional[TelegramClient] = None
        self.auth_phone: Optional[str] = None
        self.phone_code_hash: Optional[str] = None
        self.selected_channel_id: Optional[str] = None
        self.selected_channel_name: Optional[str] = None
        
        self.last_message_text: Optional[str] = None
        self.last_message_time: Optional[str] = None
        self.last_message_sender: Optional[str] = None
        self.messages_received: int = 0
        self.messages_parsed: int = 0
        self.messages_rejected: int = 0
        self.last_error: Optional[str] = None
        
        self.paper_broker = PaperBroker()
        self.resolver = InstrumentResolver()
        self.resolver.initialize()
        from app.brokers.kotak_neo import get_kotak_broker
        from app.market_data.kotak_neo_feed import get_sfeed_manager
        self.broker = get_kotak_broker()
        self.feed = get_sfeed_manager(self.broker)

    async def ensure_feed_connected(self) -> bool:
        """Connects to real Kotak SFeed if broker is authenticated."""
        try:
            if not self.broker.is_connected:
                auth_ok = await self.broker.authenticate()
                if not auth_ok:
                    return False
            if not self.feed:
                from app.market_data.kotak_neo_feed import get_sfeed_manager
                self.feed = get_sfeed_manager(self.broker)
            if not self.feed.is_connected:
                return await self.feed.connect()
            return True
        except Exception as e:
            logger.debug(f"[TELEGRAM] ensure_feed_connected: {e}")
            return False

    @classmethod
    def get_instance(cls) -> "TelegramListenerService":
        if cls._instance is None:
            cls._instance = TelegramListenerService()
        return cls._instance

    def set_client(self, client: Any):
        """Allows injecting a real or mock Telethon client (especially useful for tests)."""
        self.client = client

    def is_matching_channel(self, chat_id: Any) -> bool:
        """Verifies if incoming message chat_id matches the selected channel."""
        if not self.selected_channel_id:
            return False
        return normalize_telegram_id(chat_id) == normalize_telegram_id(self.selected_channel_id)

    async def get_status(self) -> Dict[str, Any]:
        """Sanitized status for UI consumption — NEVER returns api_hash, bot token, or session string."""
        is_connected = False
        is_authenticated = False
        auth_user_info = None

        if self.client:
            try:
                is_connected = self.client.is_connected()
                if is_connected:
                    is_authenticated = await self.client.is_user_authorized()
                    if is_authenticated:
                        try:
                            me = await self.client.get_me()
                            if me:
                                auth_user_info = {
                                    "id": me.id,
                                    "first_name": getattr(me, "first_name", "") or "",
                                    "last_name": getattr(me, "last_name", "") or "",
                                    "username": getattr(me, "username", "") or "",
                                    "phone": getattr(me, "phone", "") or ""
                                }
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"[TELEGRAM] Error checking client status: {e}")

        # Determine listener status
        if not settings.telegram_enabled:
            listener_status = "DISABLED"
        elif not self.client or not is_connected:
            listener_status = "DISCONNECTED"
        elif not is_authenticated:
            listener_status = "UNAUTHENTICATED"
        elif not self.selected_channel_id:
            listener_status = "WAITING_FOR_CHANNEL"
        elif self.is_running:
            listener_status = "RUNNING"
        else:
            listener_status = "STOPPED"

        return {
            "enabled": settings.telegram_enabled,
            "connected": is_connected,
            "authenticated": is_authenticated,
            "authenticated_user": auth_user_info,
            "listener_status": listener_status,
            "selected_channel": {
                "channel_id": self.selected_channel_id,
                "channel_name": self.selected_channel_name
            } if self.selected_channel_id else None,
            "last_message": self.last_message_text,
            "last_message_time": self.last_message_time,
            "last_message_sender": self.last_message_sender,
            "messages_received": self.messages_received,
            "messages_parsed": self.messages_parsed,
            "messages_rejected": self.messages_rejected,
            "last_error": self.last_error
        }

    async def restore_selected_channel(self):
        """Restores selected channel from database on startup."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(TelegramChannel).where(TelegramChannel.is_selected == True).order_by(TelegramChannel.id.desc())
                res = await session.execute(stmt)
                selected = res.scalars().first()
                if selected:
                    self.selected_channel_id = selected.channel_id
                    self.selected_channel_name = selected.channel_name
                    logger.info(f"[TELEGRAM] Restored selected channel: {selected.channel_name} ({selected.channel_id})")
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to restore selected channel from DB: {e}")

    async def start(self):
        """Starts Telethon user client and event listener."""
        if not settings.telegram_enabled:
            logger.info("[TELEGRAM] Telegram user client disabled in settings.")
            return

        # Restore previously selected channel from DB
        await self.restore_selected_channel()

        # If client not already injected, create standard Telethon TelegramClient
        if not self.client:
            api_id = settings.telegram_api_id
            api_hash = settings.telegram_api_hash
            session_path = settings.telegram_session_path or "data/telethon_session"

            if not api_id or not api_hash:
                logger.info("[TELEGRAM] TELEGRAM_API_ID or TELEGRAM_API_HASH not set. Waiting for user setup.")
                return

            try:
                # Ensure directory exists for session file
                session_dir = os.path.dirname(session_path)
                if session_dir and not os.path.exists(session_dir):
                    os.makedirs(session_dir, exist_ok=True)

                self.client = TelegramClient(session_path, int(api_id), api_hash)
            except Exception as e:
                self.last_error = f"Client init error: {str(e)}"
                logger.error(f"[TELEGRAM] Failed to create TelegramClient: {e}")
                return

        # Connect client with safe retry for transient sqlite database locks
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                if not self.client.is_connected():
                    await self.client.connect()

                if await self.client.is_user_authorized():
                    self._attach_event_handler()
                    self.is_running = True
                    logger.info("[TELEGRAM] Telethon user client authenticated and listener started.")
                else:
                    logger.info("[TELEGRAM] Telethon client connected but user account not authorized. Awaiting login.")
                break
            except Exception as e:
                if "database is locked" in str(e).lower() and attempt < max_retries:
                    logger.warning(f"[TELEGRAM] Session database locked. Retrying in 1s (attempt {attempt}/{max_retries})...")
                    await asyncio.sleep(1.0)
                else:
                    self.last_error = f"Connection error: {str(e)}"
                    logger.error(f"[TELEGRAM] Telethon connection failure: {e}")
                    break

    def _attach_event_handler(self):
        """Attaches Telethon NewMessage event handler."""
        if not self.client or getattr(self, '_handler_attached', False):
            return

        @self.client.on(events.NewMessage)
        async def telethon_message_handler(event):
            try:
                if not self.is_running:
                    return
                chat_id_str = str(event.chat_id)
                if not self.is_matching_channel(chat_id_str):
                    return

                msg_id = str(event.message.id)
                text = event.message.message or ""
                sender = ""
                if event.sender:
                    sender = getattr(event.sender, "username", None) or getattr(event.sender, "first_name", "") or str(event.sender_id or "")

                msg_date = event.message.date
                logger.info(f"[TELEGRAM] Received message #{msg_id} from {sender}: {text[:60]}")

                # Process message asynchronously
                await self.process_incoming_message(msg_id, chat_id_str, text, sender, received_at=msg_date)
            except Exception as e:
                logger.error(f"[TELEGRAM] Error in message handler: {e}")
        
        self._handler_attached = True

    async def stop(self):
        """Stops Telethon listener."""
        self.is_running = False
        if self.feed:
            try:
                await self.feed.disconnect()
            except Exception:
                pass
        logger.info("[TELEGRAM] Telethon listener stopped.")

    # -------------------------------------------------------------------------
    # AUTHENTICATION FLOW (Backend-Only, Never leaks credentials)
    # -------------------------------------------------------------------------

    async def send_login_code(self, phone: str) -> Dict[str, Any]:
        """Step 1 of user auth: requests login code from Telegram."""
        if not self.client:
            api_id = settings.telegram_api_id
            api_hash = settings.telegram_api_hash
            session_path = settings.telegram_session_path or "data/telethon_session"
            if not api_id or not api_hash:
                raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured in backend.")
            self.client = TelegramClient(session_path, int(api_id), api_hash)

        if not self.client.is_connected():
            await self.client.connect()

        sent = await self.client.send_code_request(phone)
        self.auth_phone = phone
        self.phone_code_hash = sent.phone_code_hash
        return {
            "status": "CODE_SENT",
            "phone": phone
        }

    async def sign_in_with_code(self, phone: str, code: str, password: Optional[str] = None) -> Dict[str, Any]:
        """Step 2 of user auth: signs in with received code and optional 2FA password."""
        if not self.client or not self.client.is_connected():
            if not self.client:
                api_id = settings.telegram_api_id
                api_hash = settings.telegram_api_hash
                session_path = settings.telegram_session_path or "data/telethon_session"
                self.client = TelegramClient(session_path, int(api_id), api_hash)
            await self.client.connect()

        try:
            user = await self.client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=self.phone_code_hash
            )
        except SessionPasswordNeededError:
            if not password:
                return {
                    "status": "2FA_REQUIRED",
                    "message": "Two-factor authentication password is required."
                }
            user = await self.client.sign_in(password=password)

        self._attach_event_handler()
        self.is_running = True

        me = await self.client.get_me()
        return {
            "status": "AUTHENTICATED",
            "user": {
                "id": me.id,
                "first_name": getattr(me, "first_name", "") or "",
                "last_name": getattr(me, "last_name", "") or "",
                "username": getattr(me, "username", "") or "",
                "phone": getattr(me, "phone", "") or ""
            }
        }

    async def logout(self) -> Dict[str, Any]:
        """Logs out from Telegram and resets authorization."""
        if self.client and self.client.is_connected():
            try:
                await self.client.log_out()
            except Exception as e:
                logger.debug(f"[TELEGRAM] Error during logout: {e}")
        self.client = None
        self.is_running = False
        self.auth_phone = None
        self.phone_code_hash = None
        return {"status": "LOGGED_OUT"}

    # -------------------------------------------------------------------------
    # CHANNEL DISCOVERY & SELECTION
    # -------------------------------------------------------------------------

    async def discover_channels(self) -> List[Dict[str, Any]]:
        """Discovers accessible Telegram dialogs/channels for the authenticated user account."""
        discovered: List[Dict[str, Any]] = []

        if self.client and self.client.is_connected():
            try:
                if await self.client.is_user_authorized():
                    dialogs = await self.client.get_dialogs()
                    for d in dialogs:
                        entity = d.entity
                        c_type = "chat"
                        if getattr(d, "is_channel", False):
                            c_type = "broadcast" if getattr(entity, "broadcast", False) else "megagroup"
                        elif getattr(d, "is_group", False):
                            c_type = "group"
                        elif getattr(d, "is_user", False):
                            continue # Skip direct 1-to-1 contacts

                        c_id = str(d.id)
                        c_name = d.name or getattr(entity, "title", str(d.id))
                        uname = getattr(entity, "username", None)

                        discovered.append({
                            "channel_id": c_id,
                            "channel_name": c_name,
                            "username": uname,
                            "channel_type": c_type,
                            "is_selected": self.is_matching_channel(c_id)
                        })
            except Exception as e:
                logger.error(f"[TELEGRAM] Error fetching dialogs: {e}")

        # Synchronize / merge discovered channels with database
        async with AsyncSessionLocal() as session:
            try:
                for c in discovered:
                    stmt = select(TelegramChannel).where(TelegramChannel.channel_id == c["channel_id"])
                    existing = (await session.execute(stmt)).scalar_one_or_none()
                    if not existing:
                        db_ch = TelegramChannel(
                            channel_id=c["channel_id"],
                            channel_name=c["channel_name"],
                            username=c.get("username"),
                            channel_type=c.get("channel_type"),
                            is_selected=c["is_selected"],
                            is_active=True
                        )
                        session.add(db_ch)
                    else:
                        existing.channel_name = c["channel_name"]
                        existing.username = c.get("username")
                        existing.channel_type = c.get("channel_type")
                        if existing.is_selected:
                            c["is_selected"] = True
                            self.selected_channel_id = existing.channel_id
                            self.selected_channel_name = existing.channel_name
                await session.commit()

                # Also retrieve any channels previously saved in DB not in current dialog list
                all_db_channels = (await session.execute(select(TelegramChannel))).scalars().all()
                existing_ids = {c["channel_id"] for c in discovered}
                for db_c in all_db_channels:
                    if db_c.channel_id not in existing_ids:
                        discovered.append({
                            "channel_id": db_c.channel_id,
                            "channel_name": db_c.channel_name,
                            "username": db_c.username,
                            "channel_type": db_c.channel_type or "channel",
                            "is_selected": db_c.is_selected
                        })
            except Exception as e:
                await session.rollback()
                logger.error(f"[TELEGRAM] DB sync error for channels: {e}")

        return discovered

    async def select_channel(self, channel_id: str, channel_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Selects the active channel for signal listening.
        Persists selection to DB and updates in-memory filter.
        """
        async with AsyncSessionLocal() as session:
            try:
                # Set all to unselected
                all_channels = (await session.execute(select(TelegramChannel))).scalars().all()
                matched = False
                for ch in all_channels:
                    if ch.channel_id == str(channel_id):
                        ch.is_selected = True
                        if channel_name:
                            ch.channel_name = channel_name
                        self.selected_channel_name = ch.channel_name
                        matched = True
                    else:
                        ch.is_selected = False

                if not matched:
                    new_ch = TelegramChannel(
                        channel_id=str(channel_id),
                        channel_name=channel_name or str(channel_id),
                        is_selected=True,
                        is_active=True
                    )
                    session.add(new_ch)
                    self.selected_channel_name = new_ch.channel_name

                await session.commit()

                self.selected_channel_id = str(channel_id)
                self.is_running = True
                logger.info(f"[TELEGRAM] Channel selected: {self.selected_channel_name} ({self.selected_channel_id})")

                return {
                    "status": "SUCCESS",
                    "channel_id": self.selected_channel_id,
                    "channel_name": self.selected_channel_name
                }
            except Exception as e:
                await session.rollback()
                logger.error(f"[TELEGRAM] Failed to select channel: {e}")
                raise e

    # -------------------------------------------------------------------------
    # MESSAGE PROCESSING & DUPLICATE PROTECTION
    # -------------------------------------------------------------------------

    async def process_incoming_message(
        self,
        message_id: str,
        channel_id: str,
        text: str,
        sender: Optional[str] = None,
        received_at: Optional[datetime] = None,
        db_session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Processes an incoming Telegram message:
        1. Persists raw message in telegram_messages table.
        2. Enforces duplicate protection via (channel_id, telegram_message_id).
        3. Parses message using signal parser.
        4. Validates & resolves contract with InstrumentResolver.
        5. Subscribes contract in market_data_service (REAL SFEED vs TEST DATA).
        6. Dispatches to TradeManager for paper trading.
        """
        if not text or not text.strip():
            return {"status": "EMPTY_TEXT", "parsed": False}

        if db_session is not None:
            return await self._process_with_session(
                db_session, message_id, channel_id, text, sender, received_at
            )

        async with AsyncSessionLocal() as session:
            return await self._process_with_session(
                session, message_id, channel_id, text, sender, received_at
            )

    async def _process_with_session(
        self,
        session: AsyncSession,
        message_id: str,
        channel_id: str,
        text: str,
        sender: Optional[str],
        received_at: Optional[datetime]
    ) -> Dict[str, Any]:
        if received_at is not None:
            recv_time = received_at if received_at.tzinfo is not None else received_at.replace(tzinfo=timezone.utc)
            recv_time = recv_time.astimezone(timezone.utc)
        else:
            recv_time = datetime.now(timezone.utc)

        # 1. DUPLICATE CHECK
        stmt = select(TelegramMessage).where(
            TelegramMessage.telegram_message_id == str(message_id),
            TelegramMessage.channel_id == str(channel_id)
        )
        existing_msg = (await session.execute(stmt)).scalar_one_or_none()
        if existing_msg:
            logger.warning(f"[TELEGRAM] DUPLICATE DETECTED: msg_id={message_id}, channel={channel_id}")
            return {
                "status": "DUPLICATE",
                "message_id": message_id,
                "parsed": False,
                "detail": "Message already processed"
            }

        # 2. Ensure channel exists in telegram_channels to satisfy foreign key
        ch_stmt = select(TelegramChannel).where(TelegramChannel.channel_id == str(channel_id))
        db_channel = (await session.execute(ch_stmt)).scalar_one_or_none()
        if not db_channel:
            db_channel = TelegramChannel(
                channel_id=str(channel_id),
                channel_name=self.selected_channel_name or str(channel_id),
                is_active=True,
                is_selected=(self.selected_channel_id == str(channel_id))
            )
            session.add(db_channel)
            await session.flush()

        self.messages_received += 1
        self.last_message_text = text[:100]
        self.last_message_time = to_utc_iso(recv_time)
        self.last_message_sender = sender

        # 3. Parse Message
        parse_result: ParseResult = parse_message(text)
        is_parsed = parse_result.parsed_successfully and parse_result.signal is not None

        # 4. Save to telegram_messages FIRST
        msg_record = TelegramMessage(
            telegram_message_id=str(message_id),
            channel_id=str(channel_id),
            sender=sender,
            received_at=recv_time,
            message_text=text,
            message_type=parse_result.message_type.value,
            parsed_successfully=is_parsed,
            processing_status="PARSED" if is_parsed else "REJECTED",
            error_message="; ".join(parse_result.validation_errors) if parse_result.validation_errors else None
        )
        session.add(msg_record)
        await session.flush()

        trade_id = None
        resolved_token = None

        if is_parsed and parse_result.message_type == TelegramMessageType.NEW_SIGNAL:
            self.messages_parsed += 1
            sig = parse_result.signal

            # Query system user & broker
            from app.database.models import User, BrokerAccount
            user_stmt = select(User).limit(1)
            user = (await session.execute(user_stmt)).scalar_one_or_none()
            user_id = user.id if user else 1

            broker_stmt = select(BrokerAccount).where(BrokerAccount.user_id == user_id).limit(1)
            broker = (await session.execute(broker_stmt)).scalar_one_or_none()
            broker_account_id = broker.id if broker else 1

            # 5. Instrument Resolution
            try:
                resolved = await self.resolver.resolve_option_contract(
                    underlying=sig.underlying,
                    strike=float(sig.strike),
                    option_type=sig.option_type,
                    expiry=None  # Force auto-selection of nearest weekly expiry
                )
                resolved_token = resolved.get("pSymbol") or str(resolved.get("instrument_token", resolved.get("token")))
                resolved_symbol = resolved.get("symbol", resolved_token)
                resolved_segment = resolved.get("exchange_segment", "nse_fo")
                resolved_trading_symbol = resolved.get("trading_symbol", resolved.get("symbol", resolved_token))

            except Exception as e:
                logger.error(f"[TELEGRAM] Instrument resolution failed for {sig.underlying} {sig.strike} {sig.option_type}: {e}")
                msg_record.processing_status = "RESOLUTION_FAILED"
                msg_record.error_message = f"Instrument resolution failed: {str(e)}"
                self.messages_rejected += 1
                await session.commit()
                return {
                    "status": "REJECTED",
                    "message_id": message_id,
                    "message_record_id": msg_record.id,
                    "parsed": True,
                    "message_type": parse_result.message_type.value,
                    "trade_id": None,
                    "instrument_token": None,
                    "validation_errors": [f"Instrument resolution failed: {str(e)}"]
                }

            # 6. Process via TradeManager (Evaluates Risk BEFORE subscribing to Market Data)
            trade_manager = TradeManager(session, self.paper_broker)
            trade = await trade_manager.process_new_signal(
                user_id=user_id,
                broker_account_id=broker_account_id,
                signal_data=sig,
                message_id=str(msg_record.id),
                resolved_token=resolved_token
            )
            trade_id = trade.id
            msg_record.trade_id = trade_id

            if trade.status == TradeState.REJECTED:
                # Risk or validation rejected the trade: do NOT subscribe to market data
                msg_record.processing_status = "RISK_REJECTED"
                self.messages_rejected += 1
                # Clean up any residual subscription if present
                market_data_service.unsubscribe(resolved_token)
                logger.warning(f"[TELEGRAM] Trade #{trade.id} was REJECTED by RiskManager. No market data subscription created.")
                await session.commit()
                return {
                    "status": "REJECTED",
                    "message_id": message_id,
                    "message_record_id": msg_record.id,
                    "parsed": True,
                    "message_type": parse_result.message_type.value,
                    "trade_id": trade_id,
                    "instrument_token": resolved_token,
                    "validation_errors": ["Trade rejected by RiskManager"]
                }

            # 7. SFeed Subscription (ONLY after TradeManager / RiskManager approval)
            msg_record.processing_status = "TRADE_CREATED"
            market_data_service.register_trade_interest(
                token=resolved_token,
                trade_id=trade_id,
                symbol=resolved_symbol,
                exchange_seg=resolved_segment,
                trading_symbol=resolved_trading_symbol,
                strike=float(sig.strike),
                option_type=sig.option_type,
                expiry=sig.expiry.isoformat() if sig.expiry else None
            )

            # Subscribe to real Kotak SFeed if connected
            try:
                feed_ok = await self.ensure_feed_connected()
                if feed_ok and self.feed:
                    await self.feed.subscribe_single(resolved_segment, resolved_token)
            except Exception as fe:
                logger.debug(f"[TELEGRAM] Real SFeed subscription notice: {fe}")

        elif is_parsed and parse_result.message_type in [
            TelegramMessageType.EXIT,
            TelegramMessageType.STOP_LOSS,
            TelegramMessageType.PARTIAL_PROFIT
        ]:
            self.messages_parsed += 1
            trade_manager = TradeManager(session, self.paper_broker)
            await trade_manager.execute_manual_exit(
                message_type=parse_result.message_type,
                channel_id=channel_id,
                timestamp=datetime.now(timezone.utc)
            )
            msg_record.processing_status = "MANUAL_EXIT_EXECUTED"
        else:
            self.messages_rejected += 1

        await session.commit()

        return {
            "status": "SUCCESS" if is_parsed else "REJECTED",
            "message_id": message_id,
            "message_record_id": msg_record.id,
            "parsed": is_parsed,
            "message_type": parse_result.message_type.value,
            "trade_id": trade_id,
            "instrument_token": resolved_token,
            "validation_errors": parse_result.validation_errors
        }

telegram_listener = TelegramListenerService.get_instance()
