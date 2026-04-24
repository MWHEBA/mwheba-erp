#!/usr/bin/env python
"""
Manual Bundle Testing Script
============================

This script performs comprehensive manual testing of the bundle creation and editing workflows.
It simulates user interactions with the bundle management system.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()

from decimal import Decimal
from django.db import transaction
from django.contrib.auth.models import User
from product.models import Product, BundleComponent
from product.services.bundle_manager import BundleManager
from product.forms import BundleForm, BundleComponentFormSet


class BundleManualTester:
    """Manual testing class for bundle functionality"""
    
    def __init__(self):
        self.bundle_manager = BundleManager()
        self.test_results = []
        
    def log_test(self, test_name, success, message=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append(f"{status} {test_name}: {message}")
        print(f"{status} {test_name}: {message}")
        
    def test_bundle_creation_workflow(self):
        """Test complete bundle creation workflow"""
        print("\n🧪 Testing Bundle Creation Workflow...")
        
        try:
            # Get available components
            components = Product.objects.filter(is_bundle=False, is_active=True)[:3]
            if len(components) < 2:
                self.log_test("Bundle Creation", False, "Not enough components available")
                return
                
            # Prepare bundle data
            bundle_data = {
                'name': 'Test Manual Bundle',
                'sku': 'MANUAL_TEST_001',
                'description': 'Bundle created during manual testing',
                'price': Decimal('100.00'),
                'is_active': True,
                'is_bundle': True
            }
            
            # Prepare components data
            components_data = [
                {
                    'component_product': components[0].id,
                    'quantity': 2
                },
                {
                    'component_product': components[1].id,
                    'quantity': 1
                }
            ]
            
            # Test bundle creation
            result = self.bundle_manager.create_bundle(bundle_data, components_data)
            
            if result['success']:
                bundle = result['bundle']
                self.log_test("Bundle Creation", True, f"Created bundle: {bundle.name}")
                
                # Verify components were created
                component_count = BundleComponent.objects.filter(bundle_product=bundle).count()
                expected_count = len(components_data)
                
                if component_count == expected_count:
                    self.log_test("Bundle Components", True, f"Created {component_count} components")
                else:
                    self.log_test("Bundle Components", False, f"Expected {expected_count}, got {component_count}")
                    
                # Test bundle stock calculation
                calculated_stock = bundle.get_calculated_stock()
                self.log_test("Stock Calculation", True, f"Bundle stock: {calculated_stock}")
                
                return bundle
            else:
                self.log_test("Bundle Creation", False, f"Error: {result.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            self.log_test("Bundle Creation", False, f"Exception: {str(e)}")
            return None
            
    def test_bundle_editing_workflow(self, bundle):
        """Test bundle editing workflow"""
        print("\n🧪 Testing Bundle Editing Workflow...")
        
        if not bundle:
            self.log_test("Bundle Editing", False, "No bundle provided for editing")
            return
            
        try:
            # Get current components
            current_components = list(BundleComponent.objects.filter(bundle_product=bundle))
            
            # Prepare new components data (modify quantities)
            new_components_data = []
            for component in current_components:
                new_components_data.append({
                    'component_product': component.component_product.id,
                    'quantity': component.quantity + 1  # Increase quantity
                })
                
            # Add a new component if available
            available_products = Product.objects.filter(
                is_bundle=False, 
                is_active=True
            ).exclude(
                id__in=[c.component_product.id for c in current_components]
            )
            
            if available_products.exists():
                new_components_data.append({
                    'component_product': available_products.first().id,
                    'quantity': 1
                })
                
            # Test component update
            result = self.bundle_manager.update_bundle_components(bundle, new_components_data)
            
            if result['success']:
                self.log_test("Bundle Editing", True, "Successfully updated bundle components")
                
                # Verify changes
                updated_count = BundleComponent.objects.filter(bundle_product=bundle).count()
                expected_count = len(new_components_data)
                
                if updated_count == expected_count:
                    self.log_test("Component Update", True, f"Updated to {updated_count} components")
                else:
                    self.log_test("Component Update", False, f"Expected {expected_count}, got {updated_count}")
                    
            else:
                self.log_test("Bundle Editing", False, f"Error: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            self.log_test("Bundle Editing", False, f"Exception: {str(e)}")
            
    def test_bundle_validation(self):
        """Test bundle validation rules"""
        print("\n🧪 Testing Bundle Validation...")
        
        try:
            # Test empty components validation
            bundle_data = {
                'name': 'Invalid Bundle',
                'sku': 'INVALID_001',
                'price': Decimal('50.00'),
                'is_bundle': True
            }
            
            result = self.bundle_manager.create_bundle(bundle_data, [])
            
            if not result['success']:
                self.log_test("Empty Components Validation", True, "Correctly rejected empty components")
            else:
                self.log_test("Empty Components Validation", False, "Should have rejected empty components")
                
            # Test duplicate SKU validation
            existing_bundle = Product.objects.filter(is_bundle=True).first()
            if existing_bundle:
                duplicate_data = {
                    'name': 'Duplicate SKU Bundle',
                    'sku': existing_bundle.sku,  # Use existing SKU
                    'price': Decimal('75.00'),
                    'is_bundle': True
                }
                
                components_data = [{
                    'component_product': Product.objects.filter(is_bundle=False).first().id,
                    'quantity': 1
                }]
                
                result = self.bundle_manager.create_bundle(duplicate_data, components_data)
                
                if not result['success']:
                    self.log_test("Duplicate SKU Validation", True, "Correctly rejected duplicate SKU")
                else:
                    self.log_test("Duplicate SKU Validation", False, "Should have rejected duplicate SKU")
                    
        except Exception as e:
            self.log_test("Bundle Validation", False, f"Exception: {str(e)}")
            
    def test_form_validation(self):
        """Test Django form validation"""
        print("\n🧪 Testing Form Validation...")
        
        try:
            # Test valid bundle form
            valid_data = {
                'name': 'Form Test Bundle',
                'sku': 'FORM_TEST_001',
                'description': 'Testing form validation',
                'price': '150.00',
                'is_active': True,
                'is_bundle': True
            }
            
            form = BundleForm(data=valid_data)
            
            if form.is_valid():
                self.log_test("Valid Form", True, "Form validation passed")
            else:
                self.log_test("Valid Form", False, f"Form errors: {form.errors}")
                
            # Test invalid form (missing required fields)
            invalid_data = {
                'name': '',  # Empty name
                'sku': '',   # Empty SKU
                'price': 'invalid_price'  # Invalid price
            }
            
            invalid_form = BundleForm(data=invalid_data)
            
            if not invalid_form.is_valid():
                self.log_test("Invalid Form", True, "Correctly rejected invalid form")
            else:
                self.log_test("Invalid Form", False, "Should have rejected invalid form")
                
        except Exception as e:
            self.log_test("Form Validation", False, f"Exception: {str(e)}")
            
    def test_admin_functionality(self):
        """Test admin interface functionality"""
        print("\n🧪 Testing Admin Functionality...")
        
        try:
            from product.admin import ProductAdmin, BundleComponentAdmin
            from django.contrib.admin.sites import AdminSite
            
            # Test ProductAdmin
            site = AdminSite()
            product_admin = ProductAdmin(Product, site)
            
            # Test bundle product display
            bundle = Product.objects.filter(is_bundle=True).first()
            if bundle:
                stock_display = product_admin.get_stock_display(bundle)
                self.log_test("Admin Stock Display", True, f"Stock display: {stock_display}")
                
                # Test inlines for bundle
                inlines = product_admin.get_inlines(None, bundle)
                has_component_inline = any('BundleComponent' in str(inline) for inline in inlines)
                
                if has_component_inline:
                    self.log_test("Admin Inlines", True, "Bundle component inline present")
                else:
                    self.log_test("Admin Inlines", False, "Bundle component inline missing")
            else:
                self.log_test("Admin Functionality", False, "No bundle available for testing")
                
        except Exception as e:
            self.log_test("Admin Functionality", False, f"Exception: {str(e)}")
            
    def cleanup_test_data(self):
        """Clean up test data"""
        print("\n🧹 Cleaning up test data...")
        
        try:
            # Delete test bundles
            test_bundles = Product.objects.filter(
                sku__in=['MANUAL_TEST_001', 'INVALID_001', 'FORM_TEST_001']
            )
            
            deleted_count = 0
            for bundle in test_bundles:
                bundle.delete()
                deleted_count += 1
                
            self.log_test("Cleanup", True, f"Deleted {deleted_count} test bundles")
            
        except Exception as e:
            self.log_test("Cleanup", False, f"Exception: {str(e)}")
            
    def run_all_tests(self):
        """Run all manual tests"""
        print("🚀 Starting Bundle Management Manual Tests")
        print("=" * 50)
        
        # Run tests
        bundle = self.test_bundle_creation_workflow()
        self.test_bundle_editing_workflow(bundle)
        self.test_bundle_validation()
        self.test_form_validation()
        self.test_admin_functionality()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Print summary
        print("\n📊 Test Summary")
        print("=" * 50)
        
        passed = sum(1 for result in self.test_results if "✅ PASS" in result)
        failed = sum(1 for result in self.test_results if "❌ FAIL" in result)
        
        print(f"Total Tests: {len(self.test_results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        if failed == 0:
            print("\n🎉 All tests passed! Bundle management system is working correctly.")
        else:
            print(f"\n⚠️  {failed} test(s) failed. Please review the issues above.")
            
        return failed == 0


if __name__ == "__main__":
    tester = BundleManualTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
