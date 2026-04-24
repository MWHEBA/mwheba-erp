"""
Governance Signals Package

This package contains thin signal adapters for various business workflows.
All signals are designed to handle non-critical side effects only, with
business logic remaining in dedicated service classes.

Key Principles:
- Thin adapters only (no business logic in signals)
- Feature flag protection for safe rollback
- Non-critical side effects only
- Signal independence (failures don't break writes)
- Integration with SignalRouter governance

Available Signal Modules:
- payroll_signals: Payroll workflow signal adapters
- auto_activation: Auto-activation signals for Governance
"""

import logging

logger = logging.getLogger('governance.signals')

# Import signal modules to ensure they are registered
try:
    from . import payroll_signals
except ImportError as e:
    logger.error(f"Failed to load payroll signal adapters: {e}")

try:
    from . import auto_activation
except ImportError as e:
    logger.error(f"Failed to load auto-activation signals: {e}")

__all__ = ['payroll_signals', 'auto_activation']