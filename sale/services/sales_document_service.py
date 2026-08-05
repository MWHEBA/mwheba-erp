"""
FIN-SAL-001 / FIN-AR-001: Sales Document Governance Service (v6.0 Master Blueprint)
Exposes SalesDocumentService matching the locked master specification.
"""
from sale.services.sales_service import SalesService

# SalesDocumentService is the official master service alias for FIN-SAL-001 & FIN-AR-001
SalesDocumentService = SalesService
