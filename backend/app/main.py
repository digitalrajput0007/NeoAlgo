from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router
from app.database.database import init_db
from app.services.telegram_listener import telegram_listener

import asyncio
from app.market_data.kotak_neo_feed import get_sfeed_manager
from app.services.entry_expiry_sweeper import entry_expiry_sweeper
from app.config import settings
from app.services.auth_service import verify_password

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Production Safety Checks (Phase 11D)
    if settings.neoalgo_env.lower() == "production":
        if not settings.neoalgo_auth_secret:
            raise RuntimeError("CRITICAL: NEOALGO_AUTH_SECRET must be set in production.")
        if not settings.neoalgo_admin_password_hash:
            raise RuntimeError("CRITICAL: NEOALGO_ADMIN_PASSWORD_HASH must be set in production.")
        # Prevent default "admin" password in production
        if verify_password("admin", settings.neoalgo_admin_password_hash):
            raise RuntimeError("CRITICAL: UNSAFE DEFAULT CREDENTIAL IN PRODUCTION. Please change the admin password.")

    # Initialize DB tables and seed default paper account
    await init_db()
    
    # Start persistent SFeed background supervisor task
    sfeed_manager = get_sfeed_manager()
    sfeed_task = asyncio.create_task(sfeed_manager.run_supervisor())
    app.state.sfeed_manager = sfeed_manager
    app.state.sfeed_task = sfeed_task

    # Allow SFeed supervisor a brief window to initiate connection if Kotak is responsive,
    # but do NOT block startup indefinitely if Kotak is unavailable.
    try:
        await asyncio.wait_for(sfeed_manager.wait_for_connected(), timeout=3.0)
    except (asyncio.TimeoutError, Exception):
        pass
    
    # Restore market data subscriptions for active non-closed trades
    from app.services.trade_recovery import restore_active_trades_subscriptions
    await restore_active_trades_subscriptions()

    # Reconcile subscriptions again if SFeed is already connected
    if sfeed_manager.is_connected:
        await sfeed_manager.reconcile_subscriptions()

    # Phase 10C: Start entry timeout sweeper (restart-safe, 30 s polling)
    expiry_task = asyncio.create_task(entry_expiry_sweeper.run())
    app.state.expiry_task = expiry_task
    
    # Start Telegram background listener if configured
    await telegram_listener.start()
    
    yield
    
    # Stop background tasks cleanly
    await telegram_listener.stop()
    await entry_expiry_sweeper.stop()
    await sfeed_manager.stop()
    if sfeed_task and not sfeed_task.done():
        sfeed_task.cancel()
        try:
            await sfeed_task
        except (asyncio.CancelledError, Exception):
            pass
    expiry_task = getattr(app.state, "expiry_task", None)
    if expiry_task and not expiry_task.done():
        expiry_task.cancel()
        try:
            await expiry_task
        except (asyncio.CancelledError, Exception):
            pass

app = FastAPI(title="Telegram Algo Trader API", lifespan=lifespan)

# Security Headers Middleware (Phase 11D)
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Dynamic CORS Configuration (Phase 11D)
origins = [origin.strip() for origin in settings.neoalgo_cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "Telegram Algo Trader API is running",
        "mode": "PAPER",
        "live_orders": "DISABLED"
    }

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "message": "Telegram Algo Trader API is running",
        "mode": "PAPER",
        "live_orders": "DISABLED"
    }

