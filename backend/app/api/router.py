from fastapi import APIRouter

from app.api.backtest_callbacks import router as backtest_callbacks_router
from app.api.backtests import router as backtests_router
from app.api.balances import router as balances_router
from app.api.market_data import router as market_data_router
from app.api.portfolios import router as portfolios_router
from app.api.positions import router as positions_router
from app.api.reports import router as reports_router
from app.api.templates import router as templates_router
from app.api.trading_operations import router as trading_operations_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(backtests_router)
api_router.include_router(backtest_callbacks_router)
api_router.include_router(portfolios_router)
api_router.include_router(balances_router)
api_router.include_router(positions_router)
api_router.include_router(trading_operations_router)
api_router.include_router(market_data_router)
api_router.include_router(templates_router)
api_router.include_router(reports_router)
