# استيراد جميع الإشارات لضمان تسجيلها
from .validation_signals import (
    pre_financial_transaction,
    FinancialTransactionSignalHandler,
    trigger_validation,
    connect_model_validation
)