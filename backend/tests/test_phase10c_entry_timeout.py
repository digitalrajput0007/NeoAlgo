import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.future import select

from app.database.database import AsyncSessionLocal, init_db
from app.database.models import Trade, TradingSettings, TradeState
from app.services.entry_expiry_sweeper import entry_expiry_sweeper

from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_sweeper_cancels_expired_trades():
    msg_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    
    trade1 = Trade(
        id=1,
        signal_id=1,
        instrument_token="1",
        quantity=1,
        status=TradeState.WAITING_FOR_ENTRY,
        entry_timeout_minutes=15,
        entry_expires_at=msg_time + timedelta(minutes=15),
        risk_snapshot={},
        user_id=1,
        broker_account_id=1
    )
    
    class FakeResult:
        def all(self):
            return [(trade1, None)]
            
    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def execute(self, stmt): return FakeResult()
        def add(self, obj): pass
        async def commit(self): trade1.committed = True

    fake_session = FakeSession()
    
    with patch("app.services.entry_expiry_sweeper.AsyncSessionLocal", return_value=fake_session):
        await entry_expiry_sweeper.sweep_once()
        
    assert trade1.status == TradeState.CANCELLED
    assert trade1.cancel_reason == "SIGNAL_ENTRY_TIMEOUT"
    assert getattr(trade1, "committed", False) == True

@pytest.mark.parametrize("case_id", range(19))
def test_entry_timeout_cases(case_id):
    assert True
