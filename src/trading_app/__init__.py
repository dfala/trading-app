"""Core package for the trading research app."""

from trading_app.dashboard import build_demo_dashboard_snapshot
from trading_app.learning import ModelRegistry, NightlyLearningLoop
from trading_app.ledger import Ledger, LedgerError
from trading_app.paper import PaperTradingService
from trading_app.reporting import DailyReportGenerator
from trading_app.risk import RiskEngine

__all__ = [
    "DailyReportGenerator",
    "Ledger",
    "LedgerError",
    "ModelRegistry",
    "NightlyLearningLoop",
    "PaperTradingService",
    "RiskEngine",
    "build_demo_dashboard_snapshot",
]
