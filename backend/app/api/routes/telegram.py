from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.database.database import get_db
from app.database.models import TelegramMessage
from app.telegram.parser import parse_message
from app.telegram.models import ParseResult
import uuid

router = APIRouter()

class TestMessageRequest(BaseModel):
    text: str

@router.post("/test/messages", response_model=ParseResult)
async def test_parse_message(request: TestMessageRequest, db: AsyncSession = Depends(get_db)):
    """
    Test endpoint for parsing Telegram messages.
    Also attempts to simulate storing it in the database to test duplicate handling.
    Does NOT place any real orders.
    """
    # Parse the message
    result = parse_message(request.text)
    
    # Simulate receiving it from a channel (for testing uniqueness)
    # We generate a mock channel ID but allow the test to potentially supply a real msg ID if needed.
    # For now, we'll just insert a dummy DB record to verify the schema constraint works.
    msg = TelegramMessage(
        telegram_message_id=f"test_{uuid.uuid4().hex[:8]}", 
        channel_id="test_channel",
        message_text=request.text,
        message_type=result.message_type,
        parsed_successfully=result.parsed_successfully,
        processing_status="TEST",
        error_message=", ".join(result.validation_errors) if result.validation_errors else None
    )
    
    db.add(msg)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Duplicate message error handling
        # For this test endpoint, we'll just ignore the duplicate error, 
        # but in reality, the listener would catch this.
        pass

    return result
