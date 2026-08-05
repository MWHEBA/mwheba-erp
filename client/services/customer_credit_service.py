"""
FIN-AR-001: Customer Credit Governance Engine Service (v6.0 Master Blueprint)
Exposes CustomerCreditGovernanceEngine matching the locked master specification.
"""
from client.services.credit_exposure_service import CreditExposureService

# CustomerCreditGovernanceEngine is the official master service name for FIN-AR-001
CustomerCreditGovernanceEngine = CreditExposureService
