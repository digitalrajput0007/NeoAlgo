"""
Comprehensive Automated Tests for InstrumentResolver and KotakNeoFeed.

Covers:
1. Instrument resolution (valid contract)
2. Explicit expiry resolution (exact match)
3. Automatic expiry resolution (nearest future weekly expiry)
4. Invalid strike handling (raises INSTRUMENT_NOT_FOUND)
5. Invalid option type handling (raises INSTRUMENT_NOT_FOUND)
6. Expired contract rejection (raises INSTRUMENT_EXPIRED)
7. Missing contract / underlying handling (raises INSTRUMENT_NOT_FOUND)
8. KotakNeoFeed session token isolation and frame verification
"""
import pytest
import pytest_asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from app.market_data.instrument_resolver import InstrumentResolver
from app.market_data.kotak_timestamps import KOTAK_FNO_EPOCH_OFFSET_SECONDS


class TestInstrumentResolverComprehensive:
    """Automated tests covering all required resolution scenarios."""

    @pytest_asyncio.fixture
    async def resolver(self):
        """Create an InstrumentResolver populated with test contracts in Kotak epoch."""
        res = InstrumentResolver("dummy_path.csv")
        now = time.time()
        kotak_now = now - KOTAK_FNO_EPOCH_OFFSET_SECONDS

        # 3 distinct future weekly expiries
        exp_week_1 = str(int(kotak_now + 86400 * 3))
        exp_week_2 = str(int(kotak_now + 86400 * 10))
        exp_week_3 = str(int(kotak_now + 86400 * 17))
        # 1 past expired expiry
        exp_past = str(int(kotak_now - 86400 * 5))

        res._cache = [
            # Expired NIFTY 25000 CE
            {
                "pSymbolName": "NIFTY",
                "pSymbol": "10001",
                "dStrikePrice": "2500000",
                "pOptionType": "CE",
                "pExpiryDate": exp_past,
                "lExpiryDate": exp_past,
                "pTrdSymbol": "NIFTYPAST25000CE",
                "pExchSeg": "nse_fo",
                "lLotSize": "65",
            },
            # Nearest future NIFTY 25000 CE (Week 1)
            {
                "pSymbolName": "NIFTY",
                "pSymbol": "10002",
                "dStrikePrice": "2500000",
                "pOptionType": "CE",
                "pExpiryDate": exp_week_1,
                "lExpiryDate": exp_week_1,
                "pTrdSymbol": "NIFTYW125000CE",
                "pExchSeg": "nse_fo",
                "lLotSize": "65",
            },
            # Far future NIFTY 25000 CE (Week 2)
            {
                "pSymbolName": "NIFTY",
                "pSymbol": "10003",
                "dStrikePrice": "2500000",
                "pOptionType": "CE",
                "pExpiryDate": exp_week_2,
                "lExpiryDate": exp_week_2,
                "pTrdSymbol": "NIFTYW225000CE",
                "pExchSeg": "nse_fo",
                "lLotSize": "65",
            },
            # NIFTY 25000 PE (Week 1)
            {
                "pSymbolName": "NIFTY",
                "pSymbol": "10004",
                "dStrikePrice": "2500000",
                "pOptionType": "PE",
                "pExpiryDate": exp_week_1,
                "lExpiryDate": exp_week_1,
                "pTrdSymbol": "NIFTYW125000PE",
                "pExchSeg": "nse_fo",
                "lLotSize": "65",
            },
            # NIFTY 25500 CE (Week 1)
            {
                "pSymbolName": "NIFTY",
                "pSymbol": "10005",
                "dStrikePrice": "2550000",
                "pOptionType": "CE",
                "pExpiryDate": exp_week_1,
                "lExpiryDate": exp_week_1,
                "pTrdSymbol": "NIFTYW125500CE",
                "pExchSeg": "nse_fo",
                "lLotSize": "65",
            },
        ]
        res._exp_week_1 = exp_week_1
        res._exp_week_2 = exp_week_2
        res._exp_past = exp_past
        return res

    @pytest.mark.asyncio
    async def test_instrument_resolution(self, resolver):
        """1. General instrument resolution returns all expected fields including lot_size."""
        result = await resolver.resolve_option_contract("NIFTY", 25000, "CE")
        assert result is not None
        assert result["instrument_token"] == "10002"
        assert result["symbol"] == "NIFTYW125000CE"
        assert result["exchange_segment"] == "nse_fo"
        assert result["lot_size"] == 65
        assert result["underlying"] == "NIFTY"
        assert result["strike"] == 25000.0
        assert result["option_type"] == "CE"

    @pytest.mark.asyncio
    async def test_explicit_expiry_exact_match(self, resolver):
        """2. Explicit expiry returns EXACT match for requested date."""
        # Request specific far future expiry (Week 2)
        result = await resolver.resolve_option_contract(
            "NIFTY", 25000, "CE", expiry=resolver._exp_week_2
        )
        assert result["instrument_token"] == "10003"
        assert result["symbol"] == "NIFTYW225000CE"
        assert result["expiry"] == resolver._exp_week_2
        assert result["selection_mode"] == "EXPLICIT_EXPIRY"

    @pytest.mark.asyncio
    async def test_nearest_future_expiry(self, resolver):
        """3. Automatic resolution selects the nearest active future weekly expiry."""
        result = await resolver.resolve_option_contract("NIFTY", 25000, "CE")
        # Must pick Week 1 (token 10002), skipping past expired (token 10001) and Week 2 (token 10003)
        assert result["instrument_token"] == "10002"
        assert result["expiry"] == resolver._exp_week_1
        assert result["selection_mode"] == "AUTO_SELECTED_NEAREST_WEEKLY_EXPIRY"

    @pytest.mark.asyncio
    async def test_invalid_strike(self, resolver):
        """4. Invalid/unavailable strike raises INSTRUMENT_NOT_FOUND."""
        with pytest.raises(ValueError) as exc:
            await resolver.resolve_option_contract("NIFTY", 99999, "CE")
        assert "INSTRUMENT_NOT_FOUND" in str(exc.value)

    @pytest.mark.asyncio
    async def test_invalid_option_type(self, resolver):
        """5. Invalid option type (e.g. 'XX' or 'CALL') raises INSTRUMENT_NOT_FOUND."""
        with pytest.raises(ValueError) as exc:
            await resolver.resolve_option_contract("NIFTY", 25000, "XX")
        assert "INSTRUMENT_NOT_FOUND" in str(exc.value)

    @pytest.mark.asyncio
    async def test_expired_contract_rejected(self, resolver):
        """6. Explicitly requested expired contract raises INSTRUMENT_EXPIRED."""
        with pytest.raises(ValueError) as exc:
            await resolver.resolve_option_contract(
                "NIFTY", 25000, "CE", expiry=resolver._exp_past
            )
        assert "INSTRUMENT_EXPIRED" in str(exc.value)

    @pytest.mark.asyncio
    async def test_missing_contract(self, resolver):
        """7. Missing underlying (e.g. 'BANKNIFTY' not in cache) raises INSTRUMENT_NOT_FOUND."""
        with pytest.raises(ValueError) as exc:
            await resolver.resolve_option_contract("BANKNIFTY", 48000, "CE")
        assert "INSTRUMENT_NOT_FOUND" in str(exc.value)


class TestKotakNeoFeedUnit:
    """Unit tests for KotakNeoFeed component."""

    @pytest.mark.asyncio
    async def test_feed_requires_connected_broker(self):
        """KotakNeoFeed refuses to connect if broker is not authenticated."""
        from app.market_data.kotak_neo_feed import KotakNeoFeed
        mock_broker = MagicMock()
        mock_broker.auth_status = "DISCONNECTED"

        feed = KotakNeoFeed(mock_broker)
        ok = await feed.connect()
        assert ok is False
        assert feed.feed_status == "AUTHENTICATION_BLOCKED"

    @pytest.mark.asyncio
    async def test_feed_uses_trading_session_not_api_token(self):
        """KotakNeoFeed must supply trading_sid and trade_token to SFeedWebSocket."""
        from app.market_data.kotak_neo_feed import KotakNeoFeed
        mock_broker = MagicMock()
        mock_broker.auth_status = "CONNECTED"
        mock_broker.trade_token = "valid_trade_token_123"
        mock_broker.trading_sid = "valid_trading_sid_456"
        mock_broker.ucc = "UCC_789"
        mock_broker.data_center = "E21"
        mock_broker.feed_url = None

        feed = KotakNeoFeed(mock_broker)

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws_instance = AsyncMock()
            mock_ws_cls.return_value = mock_ws_instance

            ok = await feed.connect()
            assert ok is True

            # Verify constructor called with trading credentials
            call_kwargs = mock_ws_cls.call_args[1]
            assert call_kwargs["access_token"] == "valid_trade_token_123"
            assert call_kwargs["sid"] == "valid_trading_sid_456"
            assert call_kwargs["auth"] == "valid_trading_sid_456"
            assert call_kwargs["ucc"] == "UCC_789"

    @pytest.mark.asyncio
    async def test_feed_subscribes_and_receives_tick(self):
        """KotakNeoFeed subscribes to single instrument and caches received LTP."""
        from app.market_data.kotak_neo_feed import KotakNeoFeed
        from neo_api_client.websocket.feed import SFeedScrip

        mock_broker = MagicMock()
        mock_broker.auth_status = "CONNECTED"
        mock_broker.trade_token = "trade_tok"
        mock_broker.trading_sid = "trade_sid"
        mock_broker.ucc = "UCC1"
        mock_broker.data_center = "E21"
        mock_broker.feed_url = None

        feed = KotakNeoFeed(mock_broker)

        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws_instance = AsyncMock()
            mock_ws_cls.return_value = mock_ws_instance

            await feed.connect()
            sub_ok = await feed.subscribe_single("nse_fo", "57796")
            assert sub_ok is True
            assert "57796" in feed.subscribed_tokens

            # Simulate an incoming SFeedScrip tick
            tick = MagicMock(spec=SFeedScrip)
            tick.instrument_token = "57796"
            tick.trading_symbol = "NIFTY2692225000CE"
            tick.exchange_segment = "nse_fo"
            tick.last_traded_price = 145.50
            feed._on_message(tick)

            # Check cache
            cached = feed.get_latest_price("57796")
            assert cached is not None
            assert cached["last_traded_price"] == 145.50
            assert cached["symbol"] == "NIFTY2692225000CE"
            assert cached["instrument_token"] == "57796"

    @pytest.mark.asyncio
    async def test_exact_instrument_token_matching_and_wrong_token_rejection(self):
        """14a & 14b: Exact instrument token matching and rejection of wrong tokens."""
        from app.market_data.kotak_neo_feed import KotakNeoFeed
        from neo_api_client.websocket.feed import SFeedScrip

        mock_broker = MagicMock()
        mock_broker.auth_status = "CONNECTED"
        mock_broker.trade_token = "trade_tok"
        mock_broker.trading_sid = "trade_sid"
        mock_broker.ucc = "UCC1"

        feed = KotakNeoFeed(mock_broker)

        # Expected token: 57796
        target_token = "57796"
        wrong_token = "99999"

        tick_wrong = MagicMock(spec=SFeedScrip)
        tick_wrong.instrument_token = wrong_token
        tick_wrong.trading_symbol = "WRONG_SYM"
        tick_wrong.exchange_segment = "nse_fo"
        tick_wrong.last_traded_price = 99.0
        feed._on_message(tick_wrong)

        # Confirm target_token is NOT populated by wrong token
        assert feed.get_latest_price(target_token) is None
        assert feed.get_latest_price(wrong_token)["last_traded_price"] == 99.0

        tick_target = MagicMock(spec=SFeedScrip)
        tick_target.instrument_token = target_token
        tick_target.trading_symbol = "NIFTY2692225000CE"
        tick_target.exchange_segment = "nse_fo"
        tick_target.last_traded_price = 152.25
        feed._on_message(tick_target)

        # Exact match confirmed
        target_data = feed.get_latest_price(target_token)
        assert target_data is not None
        assert target_data["instrument_token"] == target_token
        assert target_data["last_traded_price"] == 152.25
        assert target_data["symbol"] == "NIFTY2692225000CE"

    @pytest.mark.asyncio
    async def test_malformed_binary_frame_handling(self):
        """14c: Malformed or truncated binary frames are dropped without crashing decoder."""
        from neo_api_client.websocket.feed.protocol import decode_packet, split_batch

        dividers = {1: 100, 2: 100}

        # Empty frame
        assert split_batch(b"") == []
        assert decode_packet(b"", dividers) is None

        # Truncated header (< 9 bytes)
        assert decode_packet(b"\x05\x00\x01\x02", dividers) is None

        # Garbage packet with invalid length prefix
        garbage = b"\x02\x00\xff\xff"
        packets = split_batch(garbage)
        assert len(packets) == 0  # rejected by split_batch

    @pytest.mark.asyncio
    async def test_subscription_acknowledgement_handling(self):
        """14d: Subscription acknowledgement (message_code 1109) enriches trading symbols."""
        from neo_api_client.websocket.feed.client import SFeedWebSocket
        import json

        ws = SFeedWebSocket(user="test_u", auth="test_sid")
        ack_payload = json.dumps({
            "message_code": 1109,
            "trading_symbols": {
                "nse_fo|57796": "NIFTY2692225000CE"
            }
        })

        ws._handle_text_frame(ack_payload)
        assert ws._trading_symbols.get("nse_fo|57796") == "NIFTY2692225000CE"

    @pytest.mark.asyncio
    async def test_disconnect_and_reconnect_behavior(self):
        """14e: KotakNeoFeed cleanly updates status on disconnect."""
        from app.market_data.kotak_neo_feed import KotakNeoFeed

        mock_broker = MagicMock()
        mock_broker.auth_status = "CONNECTED"
        mock_broker.trade_token = "tok"
        mock_broker.trading_sid = "sid"
        mock_broker.ucc = "UCC"
        mock_broker.feed_url = None
        mock_broker.data_center = "E21"

        feed = KotakNeoFeed(mock_broker)
        with patch("app.market_data.kotak_neo_feed.SFeedWebSocket") as mock_ws_cls:
            mock_ws_instance = AsyncMock()
            mock_ws_cls.return_value = mock_ws_instance

            await feed.connect()
            assert feed.is_connected is True
            assert feed.feed_status == "CONNECTED"

            await feed.disconnect()
            assert feed.is_connected is False
            assert feed.feed_status == "DISCONNECTED"
            mock_ws_instance.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_binary_ltp_decoding(self):
        """14f: Decode binary MarketPicture packet into SFeedScrip with exact LTP and fields."""
        import struct
        from neo_api_client.websocket.feed.protocol import (
            decode_packet,
            HEADER_SIZE,
            MSG_MARKET_PICTURE,
            _MP_BODY,
            _DEPTH_ROW,
        )

        # Build valid binary packet for token 57796 with LTP 150.25 (paise 15025, divider 100)
        # Header layout: message_length u16, message_code u16, exchange_id i8, level u8,
        #                auction_flag u8, seq_no u8, bitmask_length u8 => 9 bytes
        header = struct.pack("<HHbBBBB", 0, MSG_MARKET_PICTURE, 2, 4, 0, 0, 0)
        body = _MP_BODY.pack(
            57796,       # token
            100,         # total_buy_qty
            200,         # total_sell_qty
            5000,        # volume_traded_today
            1726484400,  # last_trade_time
            1726484401,  # last_update_time
            14500,       # open_price (145.00)
            14000,       # close_price (140.00)
            15500,       # high_price (155.00)
            13900,       # low_price (139.00)
            15025,       # last_traded_price (150.25)
            65,          # last_trade_qty
            14800,       # avg_trade_price
            0,           # _indicative_close
            1,           # buy_depth_count
            1,           # sell_depth_count
            0,           # _trading_status
            732,         # net_chg_percent (7.32%)
            12000,       # open_interest
            750000.0,    # total_traded_value
            1025,        # net_chg (10.25)
            25000,       # upper_circuit
            5000,        # lower_circuit
            20000,       # yearly_high
            1000,        # yearly_low
            65,          # market_lot
            2,           # precision
            1,           # multiplier
        )
        fixed = body.ljust(144 - HEADER_SIZE, b"\x00")
        rows = _DEPTH_ROW.pack(65, 15025, 1) + _DEPTH_ROW.pack(65, 15050, 1)
        payload = fixed + rows
        total_len = HEADER_SIZE + len(payload)
        packet = struct.pack("<HHbBBBB", total_len, MSG_MARKET_PICTURE, 2, 4, 0, 0, 0) + payload

        dividers = {2: 100}  # exchange_id 2 = nse_fo
        decoded = decode_packet(packet, dividers)

        assert decoded is not None
        assert decoded.exchange_segment == "nse_fo"
        assert decoded.instrument_token == "57796"
        assert decoded.last_traded_price == 150.25
        assert decoded.open_price == 145.00
        assert decoded.close_price == 140.00
        assert decoded.high_price == 155.00
        assert decoded.low_price == 139.00
        assert decoded.market_lot == 65
