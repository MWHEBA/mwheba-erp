import logging

logger = logging.getLogger(__name__)
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Avg, Min, Max, Count
from django.contrib import messages
from django.urls import reverse
from decimal import Decimal
import json

from .models import (
    Supplier,
    SupplierType,
)

# Note: Pricing functionality has been removed as part of supplier categories cleanup
# The following views are no longer available:
# - price_comparison
# - service_calculator
# - ajax_calculate_price
# - supplier_services_comparison
# - category_analysis
# - bulk_price_calculator
# - add_specialized_service
# - edit_specialized_service

# All pricing-related functions have been removed as part of supplier categories cleanup