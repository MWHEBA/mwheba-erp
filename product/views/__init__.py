# -*- coding: utf-8 -*-
"""
Product Views Package
"""

# Import all views from main_views to maintain compatibility
from .main_views import *

# Import bundle-specific views
from . import bundle_analytics_views
from . import bundle_monitoring_views

from .bundle_analytics_views import (
    bundle_analytics_dashboard,
    bundle_analytics_api,
    bundle_chart_data_api,
    bundle_analytics_report_api
)

__all__ = [
    # Main views (imported with *)
    # Bundle analytics views
    'bundle_analytics_dashboard',
    'bundle_analytics_api',
    'bundle_chart_data_api',
    'bundle_analytics_report_api',
    # Bundle view modules
    'bundle_analytics_views',
    'bundle_monitoring_views'
]