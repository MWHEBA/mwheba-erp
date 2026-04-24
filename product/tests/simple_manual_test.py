"""
Simple Manual Bundle Testing
============================
"""

from decimal import Decimal
from product.models import Product, BundleComponent
from product.services.bundle_manager import BundleManager
from product.forms import BundleForm

def test_bundle_workflows():
    """Test bundle creation and editing workflows"""
    print("🚀 Starting Bundle Management Manual Tests")
    print("=" * 50)
    
    bundle_manager = BundleManager()
    results = []
    
    # Test 1: Bundle Creation
    print("\n🧪 Test 1: Bundle Creation Workflow")
    try:
        from product.models import Category, Unit
        from users.models import User
        
        components = Product.objects.filter(is_bundle=False, is_active=True)[:2]
        if len(components) < 2:
            print("❌ Not enough components available")
            return False
            
        # Get category and unit objects
        category = Category.objects.filter(is_active=True).first()
        unit = Unit.objects.filter(is_active=True).first()
        user = User.objects.first()  # Get any user for created_by
        
        if not category or not unit or not user:
            print("❌ No active category, unit, or user available")
            return False
            
        bundle_data = {
            'name': 'Manual Test Bundle',
            'sku': 'MANUAL_TEST_001',
            'description': 'Bundle created during manual testing',
            'category_id': category.id,
            'unit_id': unit.id,
            'cost_price': Decimal('80.00'),
            'selling_price': Decimal('100.00'),
            'min_stock': 5,
            'is_active': True,
            'is_bundle': True,
            'created_by_id': user.id
        }
        
        components_data = [
            {'component_product_id': components[0].id, 'required_quantity': 2},
            {'component_product_id': components[1].id, 'required_quantity': 1}
        ]
        
        success, bundle, error = bundle_manager.create_bundle(bundle_data, components_data)
        
        if success:
            print(f"✅ Created bundle: {bundle.name}")
            
            # Verify components
            component_count = BundleComponent.objects.filter(bundle_product=bundle).count()
            if component_count == 2:
                print(f"✅ Created {component_count} components")
            else:
                print(f"❌ Expected 2 components, got {component_count}")
                
            # Test stock calculation
            stock = bundle.calculated_stock
            print(f"✅ Bundle stock calculated: {stock}")
            
            results.append(True)
        else:
            print(f"❌ Bundle creation failed: {error}")
            results.append(False)
            
    except Exception as e:
        print(f"❌ Exception in bundle creation: {str(e)}")
        results.append(False)
    
    # Test 2: Bundle Editing
    print("\n🧪 Test 2: Bundle Editing Workflow")
    try:
        test_bundle = Product.objects.filter(sku='MANUAL_TEST_001').first()
        if test_bundle:
            # Get current components and modify them
            current_components = BundleComponent.objects.filter(bundle_product=test_bundle)
            new_components_data = []
            
            for component in current_components:
                new_components_data.append({
                    'component_product_id': component.component_product.id,
                    'required_quantity': component.required_quantity + 1  # Increase quantity
                })
                
            success, error = bundle_manager.update_bundle_components(test_bundle, new_components_data)
            
            if success:
                print("✅ Successfully updated bundle components")
                results.append(True)
            else:
                print(f"❌ Bundle editing failed: {error}")
                results.append(False)
        else:
            print("❌ Test bundle not found for editing")
            results.append(False)
            
    except Exception as e:
        print(f"❌ Exception in bundle editing: {str(e)}")
        results.append(False)
    
    # Test 3: Form Validation
    print("\n🧪 Test 3: Form Validation")
    try:
        # Test valid form
        valid_data = {
            'name': 'Form Test Bundle',
            'sku': 'FORM_TEST_001',
            'description': 'Testing form validation',
            'category': 19,  # Use existing category
            'unit': 13,      # Use existing unit
            'cost_price': '100.00',
            'selling_price': '150.00',
            'min_stock': '5',
            'is_active': True,
        }
        
        form = BundleForm(data=valid_data)
        if form.is_valid():
            print("✅ Valid form passed validation")
            results.append(True)
        else:
            print(f"❌ Valid form failed: {form.errors}")
            results.append(False)
            
        # Test invalid form
        invalid_data = {'name': '', 'sku': '', 'price': 'invalid'}
        invalid_form = BundleForm(data=invalid_data)
        
        if not invalid_form.is_valid():
            print("✅ Invalid form correctly rejected")
            results.append(True)
        else:
            print("❌ Invalid form should have been rejected")
            results.append(False)
            
    except Exception as e:
        print(f"❌ Exception in form validation: {str(e)}")
        results.append(False)
    
    # Test 4: Admin Interface
    print("\n🧪 Test 4: Admin Interface")
    try:
        from product.admin import ProductAdmin
        from django.contrib.admin.sites import AdminSite
        
        site = AdminSite()
        product_admin = ProductAdmin(Product, site)
        
        bundle = Product.objects.filter(is_bundle=True).first()
        if bundle:
            stock_display = product_admin.get_stock_display(bundle)
            print(f"✅ Admin stock display works: {stock_display}")
            
            inlines = product_admin.get_inlines(None, bundle)
            has_component_inline = any('BundleComponent' in str(inline) for inline in inlines)
            
            if has_component_inline:
                print("✅ Bundle component inline present in admin")
                results.append(True)
            else:
                print("❌ Bundle component inline missing")
                results.append(False)
        else:
            print("❌ No bundle available for admin testing")
            results.append(False)
            
    except Exception as e:
        print(f"❌ Exception in admin testing: {str(e)}")
        results.append(False)
    
    # Cleanup
    print("\n🧹 Cleaning up test data...")
    try:
        test_bundles = Product.objects.filter(sku__in=['MANUAL_TEST_001', 'FORM_TEST_001'])
        deleted_count = test_bundles.count()
        test_bundles.delete()
        print(f"✅ Deleted {deleted_count} test bundles")
    except Exception as e:
        print(f"❌ Cleanup failed: {str(e)}")
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    
    if passed == total:
        print("\n🎉 All tests passed! Bundle management system is working correctly.")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
        return False

# Run the tests
if __name__ == "__main__":
    test_bundle_workflows()