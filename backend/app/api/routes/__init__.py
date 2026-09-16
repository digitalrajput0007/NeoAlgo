from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_admin
from app.api.routes.telegram import router as telegram_router
from app.api.routes.trading import router as trading_router
from app.api.routes.broker import router as broker_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.journal import router as journal_router
from app.api.routes.auth import router as auth_router
from app.api.routes.profile import router as profile_router

router = APIRouter()
router.include_router(auth_router, prefix="/auth")

# Protect all other routes with the get_current_admin dependency
protected_depends = [Depends(get_current_admin)]

router.include_router(dashboard_router, dependencies=protected_depends)
router.include_router(telegram_router, prefix="/telegram", tags=["telegram"], dependencies=protected_depends)
router.include_router(trading_router, prefix="/trading", tags=["trading"], dependencies=protected_depends)
router.include_router(broker_router, prefix="/broker", tags=["broker"], dependencies=protected_depends)
router.include_router(journal_router, prefix="/journal", tags=["journal"], dependencies=protected_depends)
router.include_router(profile_router, prefix="/profile", tags=["profile"], dependencies=protected_depends)
