# Telegram Algo Trader

A production-quality automated trading platform that reads trading signals from a Telegram channel and executes trades through a supported Indian broker API (currently running in **PAPER TRADING** mode).

## Setup Instructions

### Prerequisites
* Docker & Docker Compose
* Node.js (for local frontend dev)
* Python 3.12+ (for local backend dev)

### Environment Variables
Copy `.env.example` to `.env` and fill in your details.

### Running with Docker (Development)
```bash
docker-compose -f docker-compose.dev.yml up --build
```
*(Note: A separate development compose file would be needed for local dev bind mounts. By default `docker-compose.yml` is production-ready).*

## Production Deployment

This repository is configured for production deployment on a single AWS EC2 server using Docker Compose.

**Important:** The application defaults to PAPER mode. Live trading cannot be enabled without explicit configuration and server-side safety checks.

### Production Build & Start
```bash
# Build images
docker compose build

# Start services in the background
docker compose up -d
```

### Production Operations
```bash
# Check status
docker compose ps

# View backend logs
docker compose logs -f backend

# Run database migrations
docker compose exec backend alembic upgrade head

# Stop services
docker compose down

# Restart services
docker compose restart
```

### Validation
- **Frontend Health**: Visit `http://<your-server-ip>/`
- **Backend Health**: Visit `http://<your-server-ip>/api/health`
- **Database**: Ensure PostgreSQL data persists across restarts (volume `postgres_data`).
- **Mode**: Verify that the dashboard shows "PAPER" mode and "Live Order Count" is 0.

### Local Development - Backend
```bash
cd backend
python -m venv venv
# Activate venv
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Local Development - Frontend
```bash
cd frontend
npm install
npm run dev
```

## Phase 2: Telegram Parsing & Validation

This project incorporates a robust regex-based parser that classifies incoming Telegram text into typed signals. 
Currently supported message types: `NEW_SIGNAL`, `PRICE_UPDATE`, `PARTIAL_PROFIT`, `EXIT`, `STOP_LOSS`, `INFORMATIONAL`, and `UNKNOWN`.

> [!WARNING]
> The Phase 2 components strictly stop at **validation and structural mapping**. They do NOT issue trading logic, and no real broker orders are executed through the parser.

### Test API Usage
To test the parser locally, POST raw text to `/api/test/messages`:
```json
// POST http://localhost:8000/api/test/messages
{
    "text": "NIFTY 23500 CE 15 Sept 26 Expiry\nBuy above 150\nSL below 144\nTgt above 170\nCMP 150"
}
```

### Automated Parser Tests
Run the pytest suite to verify all logic constraints (like Target > Entry) and regex extractions:
```bash
cd backend
pytest tests/test_parser.py
```

## Phase 3: Paper Trade State Machine

Phase 3 introduces the full trade lifecycle engine using `TradeManager` and a stateful `PaperBroker`. 

> [!NOTE]
> The system strictly enforces `price >= entry_trigger` for all LONG option entries. Partial exits use standard `floor()` rounding to ensure deterministic sizing.

### Injecting Prices
You can manually walk trades through their state machine (WAITING -> OPEN -> CLOSED) by injecting LTPs:
```json
// POST http://localhost:8000/api/trading/test/market-price
{
    "instrument": "PAPER_NIFTY_23500.0_CE_2026-09-15T00:00:00",
    "price": 151
}
```

### Automated Trade Tests
Tests cover the full 13 lifecycle scenarios including daily loss limits and valid target triggering:
```bash
cd backend
pytest tests/test_trade_manager.py
```
