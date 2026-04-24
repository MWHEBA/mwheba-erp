from django.test import TestCase
from django.core.exceptions import ValidationError

from utils.validators import (
    validate_phone_number,
    validate_national_id,
    extract_info_from_national_id,
    validate_positive_number,
    validate_file_extension,
    validate_image_extension,
)


class PhoneNumberValidatorTest(TestCase):
    """
    اختبارات خاصة بالتحقق من صحة أرقام الهواتف
    """

    def test_valid_phone_numbers(self):
        """اختبار أرقام هواتف صحيحة"""
        # أرقام هواتف مصرية صحيحة
        valid_numbers = [
            "01012345678",  # فودافون
            "01112345678",  # اتصالات
            "01512345678",  # وي
            "01212345678",  # أورانج
            "+201012345678",  # مع رمز الدولة
            "00201112345678",  # صيغة أخرى مع رمز الدولة
        ]

        for number in valid_numbers:
            try:
                validate_phone_number(number)
            except ValidationError:
                self.fail(f"رقم الهاتف {number} أثار خطأ تحقق على الرغم من أنه صحيح")

    def test_invalid_phone_numbers(self):
        """اختبار أرقام هواتف غير صحيحة"""
        # أرقام هواتف غير صحيحة
        invalid_numbers = [
            "0101234567",  # أقصر من المطلوب
            "010123456789",  # أطول من المطلوب
            "02012345678",  # رمز غير صحيح
            "0101234567a",  # يحتوي على حروف
            "01-01234-5678",  # يحتوي على رموز
            "+1012345678",  # رمز دولة غير صحيح
            "+20101234567",  # أقصر من المطلوب مع رمز الدولة
            "+2010123456789",  # أطول من المطلوب مع رمز الدولة
        ]

        for number in invalid_numbers:
            with self.assertRaises(
                ValidationError,
                msg=f"رقم الهاتف {number} لم يثر خطأ تحقق على الرغم من أنه غير صحيح",
            ):
                validate_phone_number(number)

    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_phone_number("1234")
            self.fail("لم يتم إثارة خطأ التحقق على الرغم من أن الرقم غير صحيح")
        except ValidationError as e:
            self.assertIn("رقم هاتف غير صالح", str(e))


class NationalIdValidatorTest(TestCase):
    """
    اختبارات خاصة بالتحقق من صحة أرقام الهوية الوطنية
    """

    def test_valid_national_ids(self):
        """اختبار أرقام هوية صحيحة"""
        from datetime import date
        
        # أرقام قومية صحيحة
        valid_ids = [
            "29901011234567",  # 1999-01-01، محافظة القاهرة، ذكر (4567 فردي)
            "30001011234568",  # 2000-01-01، محافظة القاهرة، أنثى (4568 زوجي)
            "29912311234569",  # 1999-12-31، محافظة القاهرة، ذكر (4569 فردي)
            "30512011234571",  # 2005-12-01، محافظة جنوب سيناء، ذكر (4571 فردي)
            "28506021234573",  # 1985-06-02، محافظة الإسكندرية، ذكر (4573 فردي)
            # أرقام بأكواد إدارية/استثنائية
            "29901018512345",  # 1999-01-01، كود إداري 85، أنثى
            "30512018612346",  # 2005-12-01، كود إداري 86، أنثى
            "28506018712347",  # 1985-06-02، كود إداري 87، ذكر
            "29901018812348",  # 1999-01-01، كود إداري 88، أنثى
            "30512018912349",  # 2005-12-01، كود إداري 89، ذكر
        ]

        for national_id in valid_ids:
            try:
                validate_national_id(national_id)
            except ValidationError as e:
                self.fail(
                    f"رقم الهوية {national_id} أثار خطأ تحقق على الرغم من أنه صحيح: {e}"
                )

    def test_invalid_national_ids(self):
        """اختبار أرقام هوية غير صحيحة"""
        # أرقام هوية غير صحيحة
        invalid_ids = [
            "123456789012",      # أقصر من المطلوب (12 رقم)
            "1234567890123",     # 13 رقم (يجب رفضه)
            "123456789012345",   # أطول من المطلوب (15 رقم)
            "1234abcd567890",    # يحتوي على حروف
            "123-456-7890123",   # يحتوي على رموز
            "12345678901234",    # يبدأ بـ 1 (قرن خاطئ)
            "42345678901234",    # يبدأ بـ 4 (قرن خاطئ)
            "29913321234567",    # شهر 99
            "20002401234567",    # شهر 00
            "20001321234567",    # شهر 13
            "20001001234567",    # يوم 00
            "20001321234567",    # يوم 32
            "29901019912345",    # محافظة 99
            "29901010012345",    # محافظة 00
            "29901013612345",    # محافظة 36 (خارج النطاق المسموح)
            "29901018412345",    # محافظة 84 (خارج النطاق المسموح)
            "29901019012345",    # محافظة 90 (خارج النطاق المسموح)
            "20020291234567",    # 2002-02-29 (ليس سنة كبيسة)
        ]

        for national_id in invalid_ids:
            with self.assertRaises(
                ValidationError,
                msg=f"رقم الهوية {national_id} لم يثر خطأ تحقق على الرغم من أنه غير صحيح",
            ):
                validate_national_id(national_id)

    def test_administrative_codes_national_ids(self):
        """اختبار الأرقام القومية بالأكواد الإدارية/الاستثنائية (85-89)"""
        # أرقام قومية بأكواد إدارية صحيحة
        administrative_ids = [
            "29901018512345",  # كود 85
            "30512018612346",  # كود 86
            "28506018712347",  # كود 87
            "29901018812348",  # كود 88
            "30512018912349",  # كود 89
        ]
        
        for national_id in administrative_ids:
            try:
                result = validate_national_id(national_id, raise_exception=False)
                self.assertTrue(result['valid'], f"الرقم القومي الإداري {national_id} يجب أن يكون صحيح")
                
                # التحقق من استخراج المعلومات
                info = extract_info_from_national_id(national_id)
                self.assertIsNotNone(info, f"يجب استخراج معلومات من الرقم الإداري {national_id}")
                self.assertEqual(info['governorate_name'], 'إداري/استثنائي')
                
            except ValidationError as e:
                self.fail(f"الرقم القومي الإداري {national_id} أثار خطأ: {e}")

    def test_invalid_administrative_codes(self):
        """اختبار أكواد إدارية غير صحيحة"""
        invalid_administrative_ids = [
            "29901018412345",  # كود 84 (غير مدعوم)
            "29901019012345",  # كود 90 (غير مدعوم)
            "29901018312345",  # كود 83 (غير مدعوم)
        ]
        
        for national_id in invalid_administrative_ids:
            with self.assertRaises(ValidationError, 
                                 msg=f"الكود الإداري غير المدعوم {national_id} يجب أن يثير خطأ"):
                validate_national_id(national_id)

    def test_national_id_with_birth_date_validation(self):
        """اختبار التحقق من تطابق تاريخ الميلاد"""
        from datetime import date
        
        # رقم قومي: 29901011234567 = 1999-01-01
        national_id = "29901011234567"
        
        # تاريخ ميلاد صحيح
        correct_date = date(1999, 1, 1)
        try:
            validate_national_id(national_id, birth_date=correct_date)
        except ValidationError:
            self.fail("فشل التحقق مع تاريخ ميلاد صحيح")
        
        # تاريخ ميلاد خاطئ
        wrong_date = date(1999, 1, 2)
        with self.assertRaises(ValidationError) as context:
            validate_national_id(national_id, birth_date=wrong_date)
        self.assertIn("لا يتطابق", str(context.exception))

    def test_national_id_with_gender_validation(self):
        """اختبار التحقق من تطابق الجنس"""
        
        # رقم قومي بتسلسل فردي (ذكر)
        # الأرقام 10-13 هي: 4567 - نحتاج رقم فردي
        male_id = "29901011234571"  # الرقم التسلسلي: 4571 (فردي = ذكر)
        
        try:
            validate_national_id(male_id, gender='male')
        except ValidationError:
            self.fail("فشل التحقق مع جنس صحيح (ذكر)")
        
        with self.assertRaises(ValidationError) as context:
            validate_national_id(male_id, gender='female')
        self.assertIn("لا يتطابق", str(context.exception))
        
        # رقم قومي بتسلسل زوجي (أنثى)
        female_id = "29901011234568"  # الرقم التسلسلي: 4568 (زوجي = أنثى)
        
        try:
            validate_national_id(female_id, gender='female')
        except ValidationError:
            self.fail("فشل التحقق مع جنس صحيح (أنثى)")
        
        with self.assertRaises(ValidationError) as context:
            validate_national_id(female_id, gender='male')
        self.assertIn("لا يتطابق", str(context.exception))

    def test_extract_info_from_national_id(self):
        """اختبار استخراج المعلومات من الرقم القومي"""
        from utils.validators import extract_info_from_national_id
        from datetime import date
        
        # رقم قومي: 29901011234571
        # 2: قرن 20
        # 99: سنة 1999
        # 01: شهر يناير
        # 01: يوم 1
        # 12: محافظة الدقهلية
        # 3457: تسلسلي (فردي = ذكر)
        # 1: check digit
        national_id = "29901011234571"
        info = extract_info_from_national_id(national_id)
        
        self.assertIsNotNone(info)
        self.assertTrue(info['valid'])
        self.assertEqual(info['birth_date'], date(1999, 1, 1))
        self.assertEqual(info['gender'], 'male')
        self.assertEqual(info['gender_ar'], 'ذكر')
        self.assertEqual(info['governorate_code'], 12)
        self.assertEqual(info['governorate_name'], 'الدقهلية')
        self.assertEqual(info['century'], 2)
        self.assertGreater(info['age'], 0)
        
        # رقم قومي غير صحيح
        invalid_id = "12345678901234"
        info = extract_info_from_national_id(invalid_id)
        self.assertIsNone(info)

    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_national_id("1234")
            self.fail("لم يتم إثارة خطأ التحقق على الرغم من أن الرقم غير صحيح")
        except ValidationError as e:
            self.assertIn("14 رقم", str(e))


class PositiveNumberValidatorTest(TestCase):
    """
    اختبارات خاصة بالتحقق من صحة الأرقام الموجبة
    """

    def test_valid_positive_numbers(self):
        """اختبار أرقام موجبة صحيحة"""
        valid_numbers = [
            1,
            10,
            100,
            1000,
            0.1,
            0.01,
            0.001,
            1.5,
            10.5,
            100.5,
        ]

        for number in valid_numbers:
            try:
                validate_positive_number(number)
            except ValidationError:
                self.fail(f"الرقم {number} أثار خطأ تحقق على الرغم من أنه صحيح")

    def test_invalid_positive_numbers(self):
        """اختبار أرقام غير موجبة أو غير صحيحة"""
        invalid_numbers = [
            0,
            -1,
            -10,
            -100,
            -0.1,
            -0.01,
            -0.001,
            -1.5,
            -10.5,
            -100.5,
        ]

        for number in invalid_numbers:
            with self.assertRaises(
                ValidationError,
                msg=f"الرقم {number} لم يثر خطأ تحقق على الرغم من أنه غير صحيح",
            ):
                validate_positive_number(number)

    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_positive_number(-5)
            self.fail("لم يتم إثارة خطأ التحقق على الرغم من أن الرقم غير موجب")
        except ValidationError as e:
            self.assertIn("يجب أن تكون القيمة رقم موجب", str(e))


class FileExtensionValidatorTest(TestCase):
    """
    اختبارات خاصة بالتحقق من امتدادات الملفات
    """

    def test_valid_file_extensions(self):
        """اختبار امتدادات ملفات صحيحة"""
        valid_files = [
            "document.pdf",
            "report.docx",
            "spreadsheet.xlsx",
            "presentation.pptx",
            "text.txt",
            "compressed.zip",
            "compressed.rar",
        ]

        for filename in valid_files:
            try:
                validate_file_extension(filename)
            except ValidationError:
                self.fail(f"اسم الملف {filename} أثار خطأ تحقق على الرغم من أنه صحيح")

    def test_invalid_file_extensions(self):
        """اختبار امتدادات ملفات غير صحيحة"""
        invalid_files = [
            "document.exe",
            "script.bat",
            "program.sh",
            "script.js",
            "code.php",
            "program.py",
        ]

        for filename in invalid_files:
            with self.assertRaises(
                ValidationError,
                msg=f"اسم الملف {filename} لم يثر خطأ تحقق على الرغم من أنه غير صحيح",
            ):
                validate_file_extension(filename)

    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_file_extension("program.exe")
            self.fail("لم يتم إثارة خطأ التحقق على الرغم من أن امتداد الملف غير مسموح")
        except ValidationError as e:
            self.assertIn("امتداد الملف غير مسموح به", str(e))


class ImageExtensionValidatorTest(TestCase):
    """
    اختبارات خاصة بالتحقق من امتدادات ملفات الصور
    """

    def test_valid_image_extensions(self):
        """اختبار امتدادات صور صحيحة"""
        valid_images = [
            "image.jpg",
            "photo.jpeg",
            "graphics.png",
            "icon.gif",
            "vector.svg",
        ]

        for filename in valid_images:
            try:
                validate_image_extension(filename)
            except ValidationError:
                self.fail(f"اسم الصورة {filename} أثار خطأ تحقق على الرغم من أنه صحيح")

    def test_invalid_image_extensions(self):
        """اختبار امتدادات صور غير صحيحة"""
        invalid_images = [
            "document.pdf",
            "report.docx",
            "spreadsheet.xlsx",
            "presentation.pptx",
            "text.txt",
            "compressed.zip",
        ]

        for filename in invalid_images:
            with self.assertRaises(
                ValidationError,
                msg=f"اسم الصورة {filename} لم يثر خطأ تحقق على الرغم من أنه غير صحيح",
            ):
                validate_image_extension(filename)

    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_image_extension("document.pdf")
            self.fail("لم يتم إثارة خطأ التحقق على الرغم من أن امتداد الصورة غير مسموح")
        except ValidationError as e:
            self.assertIn("امتداد الصورة غير مسموح به", str(e))
