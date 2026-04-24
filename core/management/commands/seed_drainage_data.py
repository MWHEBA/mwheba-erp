"""
أمر إضافة بيانات تجريبية: موردين، عملاء، ومنتجات مواسير وصرف صحي
"""
from django.core.management.base import BaseCommand
from django.db import transaction


SUPPLIERS_DATA = [
    {"name": "شركة النيل للمواسير والصرف", "phone": "01001234567", "city": "القاهرة", "payment_terms": "30 يوم", "contact_person": "أحمد محمد"},
    {"name": "مصنع الدلتا للبلاستيك", "phone": "01112345678", "city": "الإسكندرية", "payment_terms": "نقداً", "contact_person": "محمود علي"},
    {"name": "شركة الخليج للتوريدات الصناعية", "phone": "01223456789", "city": "الجيزة", "payment_terms": "15 يوم", "contact_person": "خالد إبراهيم"},
    {"name": "مؤسسة الرياض للمضخات", "phone": "01334567890", "city": "القاهرة", "payment_terms": "آجل 45 يوم", "contact_person": "سامي حسن"},
    {"name": "شركة الفجر للصمامات والتوصيلات", "phone": "01445678901", "city": "الإسكندرية", "payment_terms": "نقداً", "contact_person": "عمر فاروق"},
    {"name": "مصنع الوادي للحديد المجلفن", "phone": "01556789012", "city": "السويس", "payment_terms": "30 يوم", "contact_person": "طارق سعيد"},
    {"name": "شركة الأمل للفلاتر والأغطية", "phone": "01667890123", "city": "القاهرة", "payment_terms": "نقداً", "contact_person": "هاني رضا"},
    {"name": "مؤسسة الصقر للمعدات الصناعية", "phone": "01778901234", "city": "الجيزة", "payment_terms": "15 يوم", "contact_person": "وليد نصر"},
    {"name": "شركة الإتحاد للمواسير HDPE", "phone": "01889012345", "city": "القاهرة", "payment_terms": "30 يوم", "contact_person": "رامي عبدالله"},
    {"name": "مصنع النور للبلاستيك المرن", "phone": "01990123456", "city": "الإسكندرية", "payment_terms": "نقداً", "contact_person": "ياسر منصور"},
    {"name": "شركة الشرق للمضخات الغاطسة", "phone": "01001122334", "city": "القاهرة", "payment_terms": "آجل 60 يوم", "contact_person": "مصطفى كمال"},
    {"name": "مؤسسة الغرب للتوصيلات النيكل", "phone": "01112233445", "city": "الجيزة", "payment_terms": "نقداً", "contact_person": "أشرف جمال"},
    {"name": "شركة الجنوب للصمامات الهوائية", "phone": "01223344556", "city": "أسيوط", "payment_terms": "15 يوم", "contact_person": "حسام الدين"},
    {"name": "مصنع الشمال للأنابيب GRP", "phone": "01334455667", "city": "الإسكندرية", "payment_terms": "30 يوم", "contact_person": "كريم عادل"},
    {"name": "شركة الوسط للمعدات الصحية", "phone": "01445566778", "city": "القاهرة", "payment_terms": "نقداً", "contact_person": "نادر فتحي"},
    {"name": "مؤسسة الأهرام للتوريدات", "phone": "01556677889", "city": "الجيزة", "payment_terms": "30 يوم", "contact_person": "سيد عبدالرحمن"},
    {"name": "شركة الكرنك للمضخات الصناعية", "phone": "01667788990", "city": "الأقصر", "payment_terms": "آجل 30 يوم", "contact_person": "محمد الصعيدي"},
    {"name": "مصنع الإسكندرية للحديد الزهر", "phone": "01778899001", "city": "الإسكندرية", "payment_terms": "نقداً", "contact_person": "عبدالعزيز حافظ"},
    {"name": "شركة القاهرة للفلاتر الشبكية", "phone": "01889900112", "city": "القاهرة", "payment_terms": "15 يوم", "contact_person": "إيهاب سلامة"},
    {"name": "مؤسسة الجيزة للأدوات الصناعية", "phone": "01990011223", "city": "الجيزة", "payment_terms": "نقداً", "contact_person": "تامر حلمي"},
    {"name": "شركة البحر الأحمر للتوريدات", "phone": "01001234568", "city": "الغردقة", "payment_terms": "30 يوم", "contact_person": "أيمن شوقي"},
    {"name": "مصنع سيناء للمواسير PP", "phone": "01112345679", "city": "العريش", "payment_terms": "نقداً", "contact_person": "جمال الشيخ"},
    {"name": "شركة الفيوم للصمامات والأجهزة", "phone": "01223456780", "city": "الفيوم", "payment_terms": "15 يوم", "contact_person": "صلاح الدين"},
    {"name": "مؤسسة المنيا للمعدات الهيدروليكية", "phone": "01334567891", "city": "المنيا", "payment_terms": "30 يوم", "contact_person": "عصام توفيق"},
    {"name": "شركة بورسعيد للتوصيلات البحرية", "phone": "01445678902", "city": "بورسعيد", "payment_terms": "آجل 45 يوم", "contact_person": "فريد البحراوي"},
]

CUSTOMERS_DATA = [
    {"name": "مقاولون عرب للإنشاءات", "company_name": "مقاولون عرب", "phone": "01501234567", "city": "القاهرة", "client_type": "company", "credit_limit": 500000},
    {"name": "شركة الحسن للمقاولات", "company_name": "الحسن للمقاولات", "phone": "01612345678", "city": "الجيزة", "client_type": "company", "credit_limit": 300000},
    {"name": "مهندس كريم الصرف الصحي", "company_name": "", "phone": "01723456789", "city": "القاهرة", "client_type": "individual", "credit_limit": 50000},
    {"name": "بلدية مدينة نصر", "company_name": "بلدية مدينة نصر", "phone": "01834567890", "city": "القاهرة", "client_type": "government", "credit_limit": 1000000},
    {"name": "شركة الإعمار للتطوير العقاري", "company_name": "الإعمار للتطوير", "phone": "01945678901", "city": "الإسكندرية", "client_type": "company", "credit_limit": 750000},
    {"name": "مقاولات الخليج المصرية", "company_name": "الخليج المصرية", "phone": "01056789012", "city": "القاهرة", "client_type": "company", "credit_limit": 400000},
    {"name": "محافظة الجيزة - قطاع الصرف", "company_name": "محافظة الجيزة", "phone": "01167890123", "city": "الجيزة", "client_type": "government", "credit_limit": 2000000},
    {"name": "مهندس سامر البناء", "company_name": "", "phone": "01278901234", "city": "الإسكندرية", "client_type": "individual", "credit_limit": 30000},
    {"name": "شركة النهضة للمقاولات العامة", "company_name": "النهضة للمقاولات", "phone": "01389012345", "city": "القاهرة", "client_type": "company", "credit_limit": 600000},
    {"name": "هيئة الصرف الصحي بالقاهرة", "company_name": "هيئة الصرف الصحي", "phone": "01490123456", "city": "القاهرة", "client_type": "government", "credit_limit": 5000000},
    {"name": "شركة الأمل للإنشاءات", "company_name": "الأمل للإنشاءات", "phone": "01501234568", "city": "الجيزة", "client_type": "company", "credit_limit": 250000},
    {"name": "مقاول أحمد الصرف الصحي", "company_name": "", "phone": "01612345679", "city": "القاهرة", "client_type": "individual", "credit_limit": 80000},
    {"name": "شركة الوطن للتطوير والبناء", "company_name": "الوطن للتطوير", "phone": "01723456780", "city": "الإسكندرية", "client_type": "company", "credit_limit": 450000},
    {"name": "وحدة محلية شبرا الخيمة", "company_name": "وحدة شبرا الخيمة", "phone": "01834567891", "city": "القاهرة", "client_type": "government", "credit_limit": 800000},
    {"name": "شركة الفجر للمقاولات الصناعية", "company_name": "الفجر للمقاولات", "phone": "01945678902", "city": "السويس", "client_type": "company", "credit_limit": 350000},
    {"name": "مهندس طارق الأنابيب", "company_name": "", "phone": "01056789013", "city": "الجيزة", "client_type": "individual", "credit_limit": 60000},
    {"name": "شركة الشروق للإنشاءات الكبرى", "company_name": "الشروق للإنشاءات", "phone": "01167890124", "city": "القاهرة", "client_type": "company", "credit_limit": 900000},
    {"name": "هيئة الصرف الصحي بالإسكندرية", "company_name": "هيئة الصرف الإسكندرية", "phone": "01278901235", "city": "الإسكندرية", "client_type": "government", "credit_limit": 3000000},
    {"name": "شركة الدلتا للمقاولات", "company_name": "الدلتا للمقاولات", "phone": "01389012346", "city": "المنصورة", "client_type": "company", "credit_limit": 200000},
    {"name": "مقاول حسين الصرف", "company_name": "", "phone": "01490123457", "city": "أسيوط", "client_type": "individual", "credit_limit": 40000},
    {"name": "شركة الصعيد للإنشاءات", "company_name": "الصعيد للإنشاءات", "phone": "01501234569", "city": "أسيوط", "client_type": "company", "credit_limit": 150000},
    {"name": "محافظة الإسكندرية - الصرف الصحي", "company_name": "محافظة الإسكندرية", "phone": "01612345680", "city": "الإسكندرية", "client_type": "government", "credit_limit": 4000000},
    {"name": "شركة الربيع للمقاولات والبناء", "company_name": "الربيع للمقاولات", "phone": "01723456781", "city": "القاهرة", "client_type": "company", "credit_limit": 280000},
    {"name": "مهندس وليد الأنظمة الصحية", "company_name": "", "phone": "01834567892", "city": "الجيزة", "client_type": "individual", "credit_limit": 70000},
    {"name": "شركة الإسكندرية للمقاولات البحرية", "company_name": "الإسكندرية البحرية", "phone": "01945678903", "city": "الإسكندرية", "client_type": "company", "credit_limit": 550000},
]

PRODUCTS_DATA = [
    # 1. مواسير وصرف
    {"name": "ماسورة PVC للصرف الصحي", "sku": "DRN-PVC-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "45.00", "selling_price": "65.00", "item_type": "general", "description": "ماسورة PVC عالية الجودة للصرف الصحي"},
    {"name": "ماسورة HDPE للصرف الصحي", "sku": "DRN-HDPE-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "85.00", "selling_price": "120.00", "item_type": "general", "description": "ماسورة HDPE مقاومة للضغط والتآكل"},
    {"name": "ماسورة GRP للصرف الصحي", "sku": "DRN-GRP-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "150.00", "selling_price": "220.00", "item_type": "general", "description": "ماسورة GRP للمشاريع الكبرى"},
    {"name": "ماسورة PP للصرف الصحي", "sku": "DRN-PP-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "60.00", "selling_price": "90.00", "item_type": "general", "description": "ماسورة بولي بروبيلين للصرف الصحي"},
    {"name": "ماسورة بلاستيك مرنة للصرف الصحي", "sku": "DRN-FLEX-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "35.00", "selling_price": "55.00", "item_type": "general", "description": "ماسورة بلاستيك مرنة سهلة التركيب"},
    {"name": "ماسورة حديد مجلفن للصرف الصحي", "sku": "DRN-GALV-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "120.00", "selling_price": "175.00", "item_type": "general", "description": "ماسورة حديد مجلفن مقاومة للصدأ"},
    {"name": "ماسورة ضغط عالي للأنابيب البلاستيكية", "sku": "DRN-HP-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "95.00", "selling_price": "140.00", "item_type": "general", "description": "ماسورة تتحمل ضغط عالي للأنابيب البلاستيكية"},
    # 2. وصلات وتوصيلات
    {"name": "وصلة PVC للصرف الصحي", "sku": "CON-PVC-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "15.00", "selling_price": "25.00", "item_type": "general", "description": "وصلة PVC لتوصيل مواسير الصرف الصحي"},
    {"name": "وصلة مرنة لتوصيل مواسير الصرف الصحي", "sku": "CON-FLEX-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "20.00", "selling_price": "32.00", "item_type": "general", "description": "وصلة مرنة لتوصيل مواسير الصرف الصحي"},
    {"name": "وصلة حديد مقاوم للصدأ", "sku": "CON-SS-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "55.00", "selling_price": "80.00", "item_type": "general", "description": "وصلة من الحديد المقاوم للصدأ"},
    {"name": "وصلة انضغاطية لمواسير الصرف", "sku": "CON-COMP-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "30.00", "selling_price": "45.00", "item_type": "general", "description": "وصلة انضغاطية سهلة التركيب"},
    {"name": "وصلة خيطية للصرف الصحي", "sku": "CON-THRD-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "18.00", "selling_price": "28.00", "item_type": "general", "description": "وصلة خيطية للصرف الصحي"},
    # 3. فلاتر وأغطية
    {"name": "فلتر شبكي لتصفية المياه", "sku": "FLT-MESH-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "40.00", "selling_price": "60.00", "item_type": "general", "description": "فلتر شبكي لتصفية مياه الصرف الصحي"},
    {"name": "غطاء بلاعة حديدي", "sku": "CVR-IRON-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "75.00", "selling_price": "110.00", "item_type": "general", "description": "غطاء بلاعة من الحديد الصلب"},
    {"name": "غطاء بلاعة فولاذ مقاوم للصدأ", "sku": "CVR-SS-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "120.00", "selling_price": "175.00", "item_type": "general", "description": "غطاء بلاعة من الفولاذ المقاوم للصدأ"},
    {"name": "غطاء بلاعة حديد زهر", "sku": "CVR-CI-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "90.00", "selling_price": "130.00", "item_type": "general", "description": "غطاء بلاعة من الحديد الزهر"},
    {"name": "فلتر معقم لمياه الصرف الصحي", "sku": "FLT-STER-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "200.00", "selling_price": "290.00", "item_type": "general", "description": "فلتر معقم لمعالجة مياه الصرف الصحي"},
    {"name": "غطاء بلاعة حديد مجلفن", "sku": "CVR-GALV-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "65.00", "selling_price": "95.00", "item_type": "general", "description": "غطاء بلاعة من الحديد المجلفن"},
    # 4. مضخات وأجهزة
    {"name": "مضخة مياه صرف صحي منزلية", "sku": "PMP-DOM-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "800.00", "selling_price": "1200.00", "item_type": "general", "description": "مضخة مياه صرف صحي للاستخدام المنزلي"},
    {"name": "مضخة رفع مياه صرف صحي عالية الضغط", "sku": "PMP-HP-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "2500.00", "selling_price": "3500.00", "item_type": "general", "description": "مضخة رفع مياه صرف صحي عالية الضغط"},
    {"name": "مضخة طرد مركزي للصرف الصحي", "sku": "PMP-CENT-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "1800.00", "selling_price": "2600.00", "item_type": "general", "description": "مضخة طرد مركزي للصرف الصحي"},
    {"name": "مضخة غاطسة لصرف المياه", "sku": "PMP-SUB-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "1200.00", "selling_price": "1750.00", "item_type": "general", "description": "مضخة غاطسة لصرف المياه"},
    {"name": "جهاز قياس تدفق المياه", "sku": "DEV-FLOW-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "500.00", "selling_price": "750.00", "item_type": "general", "description": "جهاز قياس تدفق المياه الرقمي"},
    {"name": "مضخة مياه ذاتية الشفط للصرف الصحي", "sku": "PMP-SELF-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "950.00", "selling_price": "1400.00", "item_type": "general", "description": "مضخة مياه ذاتية الشفط للصرف الصحي"},
    {"name": "مضخة مياه صرف صحي صناعية", "sku": "PMP-IND-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "4500.00", "selling_price": "6500.00", "item_type": "general", "description": "مضخة مياه صرف صحي للاستخدام الصناعي"},
    # 5. صمامات وتوصيلات
    {"name": "صمام فحص للصرف الصحي", "sku": "VLV-CHK-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "80.00", "selling_price": "120.00", "item_type": "general", "description": "صمام فحص لمنع الارتداد في الصرف الصحي"},
    {"name": "صمام هوائي للصرف الصحي", "sku": "VLV-AIR-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "65.00", "selling_price": "95.00", "item_type": "general", "description": "صمام هوائي لتهوية منظومة الصرف الصحي"},
    {"name": "صمام أمان لمنظومات الصرف الصحي", "sku": "VLV-SAF-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "110.00", "selling_price": "160.00", "item_type": "general", "description": "صمام أمان لمنظومات الصرف الصحي"},
    {"name": "صمام تحكم لمنظومة الصرف الصحي", "sku": "VLV-CTL-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "140.00", "selling_price": "200.00", "item_type": "general", "description": "صمام تحكم لمنظومة الصرف الصحي"},
    {"name": "صمام تصريف الضغط الزائد", "sku": "VLV-REL-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "95.00", "selling_price": "140.00", "item_type": "general", "description": "صمام تصريف الضغط الزائد للصرف الصحي"},
    # 6. نواكل (نيكل)
    {"name": "وصلة نيكل للمواسير", "sku": "NKL-CON-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "45.00", "selling_price": "70.00", "item_type": "general", "description": "وصلة نيكل عالية الجودة للمواسير"},
    {"name": "غطاء بلاعة نيكل", "sku": "NKL-CVR-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "180.00", "selling_price": "260.00", "item_type": "general", "description": "غطاء بلاعة مصنوع من النيكل"},
    {"name": "صمام فحص من النيكل", "sku": "NKL-VLV-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "220.00", "selling_price": "320.00", "item_type": "general", "description": "صمام فحص من النيكل مقاوم للتآكل"},
    {"name": "وصلة خيطية نيكل", "sku": "NKL-THRD-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "55.00", "selling_price": "80.00", "item_type": "general", "description": "وصلة خيطية من النيكل"},
    {"name": "مضخة مياه مصنوعة من النيكل", "sku": "NKL-PMP-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "3500.00", "selling_price": "5000.00", "item_type": "general", "description": "مضخة مياه مصنوعة من النيكل للبيئات القاسية"},
    {"name": "تركيبات نيكل للصرف الصحي", "sku": "NKL-FIT-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "70.00", "selling_price": "100.00", "item_type": "general", "description": "تركيبات نيكل للصرف الصحي"},
    {"name": "خرطوم نيكل مرن", "sku": "NKL-HOSE-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "130.00", "selling_price": "190.00", "item_type": "general", "description": "خرطوم نيكل مرن للصرف الصحي"},
    {"name": "فلتر نيكل للمياه", "sku": "NKL-FLT-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "250.00", "selling_price": "360.00", "item_type": "general", "description": "فلتر نيكل لتصفية المياه"},
    {"name": "حلقة تثبيت نيكل", "sku": "NKL-RING-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "25.00", "selling_price": "38.00", "item_type": "general", "description": "حلقة تثبيت من النيكل"},
    {"name": "قطع غيار للمضخات من النيكل", "sku": "NKL-PART-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "160.00", "selling_price": "230.00", "item_type": "general", "description": "قطع غيار للمضخات مصنوعة من النيكل"},
    # 7. أدوات ومعدات صيانة
    {"name": "أدوات تنظيف بلاعات نيكل", "sku": "MNT-CLN-001", "category_name": "مواسير وصرف صحي", "unit_name": "طقم", "cost_price": "300.00", "selling_price": "450.00", "item_type": "general", "description": "طقم أدوات تنظيف بلاعات نيكل"},
    {"name": "مفاتيح وأدوات نيكل للصرف الصحي", "sku": "MNT-TOOL-001", "category_name": "مواسير وصرف صحي", "unit_name": "طقم", "cost_price": "400.00", "selling_price": "580.00", "item_type": "general", "description": "طقم مفاتيح وأدوات نيكل للصرف الصحي"},
    {"name": "معدات صيانة الأنابيب النيكل", "sku": "MNT-PIPE-001", "category_name": "مواسير وصرف صحي", "unit_name": "طقم", "cost_price": "550.00", "selling_price": "800.00", "item_type": "general", "description": "معدات صيانة الأنابيب النيكل"},
    {"name": "خرطوم بلاستيك مرن للصرف الصحي", "sku": "MNT-HOSE-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "28.00", "selling_price": "42.00", "item_type": "general", "description": "خرطوم بلاستيك مرن للصرف الصحي"},
    # 8. قطع غيار وصناعات أخرى
    {"name": "قطع غيار نيكل للمضخات", "sku": "SPA-NKL-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "190.00", "selling_price": "275.00", "item_type": "general", "description": "قطع غيار نيكل للمضخات الصناعية"},
    {"name": "أنابيب نيكل مقاومة للتآكل والصدمات", "sku": "SPA-PIPE-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "280.00", "selling_price": "400.00", "item_type": "general", "description": "أنابيب نيكل مقاومة للتآكل والصدمات"},
    {"name": "فلتر نيكل للصرف الصحي", "sku": "SPA-FLT-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "210.00", "selling_price": "300.00", "item_type": "general", "description": "فلتر نيكل للصرف الصحي"},
    {"name": "تركيبات نيكل للصرف الصحي المتخصصة", "sku": "SPA-FIT-001", "category_name": "مواسير وصرف صحي", "unit_name": "قطعة", "cost_price": "85.00", "selling_price": "125.00", "item_type": "general", "description": "تركيبات نيكل متخصصة للصرف الصحي"},
]


class Command(BaseCommand):
    help = 'إضافة بيانات تجريبية: موردين وعملاء ومنتجات مواسير وصرف صحي'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='معاينة البيانات بدون حفظ')

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  وضع المعاينة - لن يتم حفظ أي بيانات'))

        self._add_category(dry_run)
        self._add_suppliers(dry_run)
        self._add_customers(dry_run)
        self._add_products(dry_run)

        self.stdout.write(self.style.SUCCESS('\n🎉 تمت العملية بنجاح!'))

    def _add_category(self, dry_run):
        from product.models import Category
        self.stdout.write('\n📁 إضافة تصنيفات المنتجات...')

        # التصنيف الرئيسي
        root, _ = Category.objects.get_or_create(
            name='مواسير وصرف صحي',
            defaults={'description': 'مواسير وتوصيلات وأجهزة الصرف الصحي'}
        )

        # التصنيفات الفرعية
        sub_categories = [
            ('مواسير وصرف', 'مواسير PVC وHDPE وGRP وPP والحديد المجلفن'),
            ('وصلات وتوصيلات', 'وصلات PVC والمرنة والانضغاطية والخيطية'),
            ('فلاتر وأغطية', 'فلاتر شبكية وأغطية بلاعات بأنواعها'),
            ('مضخات وأجهزة', 'مضخات الصرف الصحي وأجهزة القياس'),
            ('صمامات وتوصيلات', 'صمامات الفحص والهوائية والأمان والتحكم'),
            ('نواكل (منتجات النيكل)', 'وصلات وأغطية وصمامات وتركيبات النيكل'),
            ('أدوات ومعدات صيانة', 'أدوات تنظيف وصيانة الأنابيب والبلاعات'),
            ('قطع غيار وصناعات أخرى', 'قطع غيار المضخات والأنابيب النيكل'),
        ]

        created_count = 0
        for name, desc in sub_categories:
            _, created = Category.objects.get_or_create(
                name=name,
                defaults={'parent': root, 'description': desc}
            )
            if created:
                created_count += 1

        self.stdout.write(f'  ✅ تم معالجة التصنيف الرئيسي + {len(sub_categories)} تصنيف فرعي (جديد: {created_count})')

    def _add_suppliers(self, dry_run):
        from supplier.models import Supplier, SupplierType
        self.stdout.write('\n🏭 إضافة الموردين...')

        supplier_type = SupplierType.objects.filter(code='product_supplier').first()
        if not supplier_type:
            self.stdout.write(self.style.ERROR('  ❌ لم يتم العثور على نوع المورد "product_supplier"'))
            return

        created_count = 0
        skipped_count = 0
        for data in SUPPLIERS_DATA:
            exists = Supplier.objects.filter(name=data['name']).exists()
            if exists:
                skipped_count += 1
                continue
            if not dry_run:
                Supplier.objects.create(
                    name=data['name'],
                    phone=data['phone'],
                    city=data['city'],
                    payment_terms=data['payment_terms'],
                    contact_person=data['contact_person'],
                    primary_type=supplier_type,
                    country='مصر',
                    is_active=True,
                )
            created_count += 1

        self.stdout.write(f'  ✅ تم إضافة {created_count} مورد جديد، تم تخطي {skipped_count} موجود')

    def _add_customers(self, dry_run):
        from client.models import Customer
        self.stdout.write('\n👥 إضافة العملاء...')

        # Get next available code number
        last = Customer.objects.filter(code__startswith='CUS').order_by('-code').first()
        if last:
            try:
                next_num = int(last.code.replace('CUS', '')) + 1
            except ValueError:
                next_num = 1
        else:
            next_num = 1

        created_count = 0
        skipped_count = 0
        for data in CUSTOMERS_DATA:
            exists = Customer.objects.filter(name=data['name']).exists()
            if exists:
                skipped_count += 1
                continue
            if not dry_run:
                code = f"CUS{next_num:03d}"
                while Customer.objects.filter(code=code).exists():
                    next_num += 1
                    code = f"CUS{next_num:03d}"

                Customer.objects.create(
                    name=data['name'],
                    company_name=data.get('company_name', ''),
                    phone=data['phone'],
                    city=data['city'],
                    client_type=data['client_type'],
                    credit_limit=data['credit_limit'],
                    code=code,
                    is_active=True,
                )
                next_num += 1
            created_count += 1

        self.stdout.write(f'  ✅ تم إضافة {created_count} عميل جديد، تم تخطي {skipped_count} موجود')

    def _add_products(self, dry_run):
        from product.models import Product, Category, Unit
        self.stdout.write('\n📦 إضافة المنتجات...')

        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('  ❌ لا يوجد مستخدم في النظام'))
            return

        category = Category.objects.filter(name='مواسير وصرف صحي').first()
        if not category:
            self.stdout.write(self.style.ERROR('  ❌ لم يتم العثور على تصنيف المنتجات'))
            return

        units = {u.name: u for u in Unit.objects.all()}

        created_count = 0
        skipped_count = 0
        for data in PRODUCTS_DATA:
            exists = Product.objects.filter(sku=data['sku']).exists()
            if exists:
                skipped_count += 1
                continue

            unit = units.get(data['unit_name']) or units.get('قطعة')
            if not unit:
                self.stdout.write(self.style.WARNING(f'  ⚠️  وحدة غير موجودة: {data["unit_name"]}'))
                continue

            if not dry_run:
                Product.objects.create(
                    name=data['name'],
                    sku=data['sku'],
                    category=category,
                    unit=unit,
                    cost_price=data['cost_price'],
                    selling_price=data['selling_price'],
                    item_type=data['item_type'],
                    description=data.get('description', ''),
                    min_stock=5,
                    is_active=True,
                    is_featured=False,
                    tax_rate='0.00',
                    discount_rate='0.00',
                    created_by=admin_user,
                )
            created_count += 1

        self.stdout.write(f'  ✅ تم إضافة {created_count} منتج جديد، تم تخطي {skipped_count} موجود')
