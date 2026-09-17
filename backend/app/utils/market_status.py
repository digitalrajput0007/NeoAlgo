from datetime import datetime
import pytz

def get_market_status() -> str:
    """
    Determines the current Indian market status based on date/time.
    Returns one of: OPEN, PRE-OPEN, CLOSED, UNKNOWN
    """
    try:
        ist_tz = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist_tz)
        
        # Check weekends
        if now_ist.weekday() >= 5: # 5 = Saturday, 6 = Sunday
            return "CLOSED"
            
        current_time = now_ist.time()
        
        pre_open_start = datetime.strptime("09:00:00", "%H:%M:%S").time()
        market_open = datetime.strptime("09:15:00", "%H:%M:%S").time()
        market_close = datetime.strptime("15:30:00", "%H:%M:%S").time()
        
        if current_time >= market_close or current_time < pre_open_start:
            return "CLOSED"
        elif pre_open_start <= current_time < market_open:
            return "PRE-OPEN"
        elif market_open <= current_time < market_close:
            return "OPEN"
            
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"
