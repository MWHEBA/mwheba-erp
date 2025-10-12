from django.test import TestCase
from django.core.exceptions import ValidationError

from utils.validators import (
    validate_phone_number, validate_national_id, validate_positive_number,
    validate_file_extension, validate_image_extension
)


class PhoneNumberValidatorTest(TestCase):
    """
    اختبارات خاصة بالتحقق من صحة أرقام الهواتف
    """
    
    def test_valid_phone_numbers(self):
        """اختبار أرقام هواتف صحيحة"""
        # أرقام هواتف مصرية صحيحة
        valid_numbers = [
            '01012345678',    # فودافون
            '01112345678',    # اتصالات
            '01512345678',    # وي
            '01212345678',    # أورانج
            '+201012345678',  # مع رمز الدولة
            '00201112345678', # صيغة أخرى مع رمز الدولة
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
            '0101234567',      # أقصر من المطلوب
            '010123456789',    # أطول من المطلوب
            '02012345678',     # رمز غير صحيح
            '0101234567a',     # يحتوي على حروف
            '01-01234-5678',   # يحتوي على رموز
            '+1012345678',     # رمز دولة غير صحيح
            '+20101234567',    # أقصر من المطلوب مع رمز الدولة
            '+2010123456789',  # أطول من المطلوب مع رمز الدولة
        ]
        
        for number in invalid_numbers:
            with self.assertRaises(ValidationError, msg=f"رقم الهاتف {number} لم يثر خطأ تحقق على الرغم من أنه غير صحيح"):
                validate_phone_number(number)
    
    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_phone_number('1234')
            self.fail("لم يتم إثارة خطأ التحقق على الرغم من أن الرقم غير صحيح")
        except ValidationError as e:
            self.assertIn("رقم هاتف غير صالح", str(e))


class NationalIdValidatorTest(TestCase):
    """
    اختبارات خاصة بالتحقق من صحة أرقام الهوية الوطنية
    """
    
    def test_valid_national_ids(self):
        """اختبار أرقام هوية صحيحة"""
        # نستخدم أرقام وهمية للاختبار
        valid_ids = [
            '29101012345678',  # صيغة 14 رقم
            '2910101234567',   # صيغة 13 رقم
        ]
        
        for national_id in valid_ids:
            try:
                validate_national_id(national_id)
            except ValidationError:
                self.fail(f"رقم الهوية {national_id} أثار خطأ تحقق على الرغم من أنه صحيح")
    
    def test_invalid_national_ids(self):
        """اختبار أرقام هوية غير صحيحة"""
        # أرقام هوية غير صحيحة
        invalid_ids = [
            '123456789012',    # أقصر من المطلوب
            '123456789012345', # أطول من المطلوب
            '1234abcd56789',   # يحتوي على حروف
            '123-456-7890123', # يحتوي على رموز
        ]
        
        for national_id in invalid_ids:
            with self.assertRaises(ValidationError, msg=f"رقم الهوية {national_id} لم يثر خطأ تحقق على الرغم من أنه غير صحيح"):
                validate_national_id(national_id)
    
    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_national_id('1234')
            self.fail("لم يتم إثارة خطأ التحقق على الرغم من أن الرقم غير صحيح")
        except ValidationError as e:
            self.assertIn("رقم هوية وطنية غير صالح", str(e))


class PositiveNumberValidatorTest(TestCase):
    """
    اختبارات خاصة بالتحقق من صحة الأرقام الموجبة
    """
    
    def test_valid_positive_numbers(self):
        """اختبار أرقام موجبة صحيحة"""
        valid_numbers = [
            1, 10, 100, 1000, 0.1, 0.01, 0.001, 1.5, 10.5, 100.5,
        ]
        
        for number in valid_numbers:
            try:
                validate_positive_number(number)
            except ValidationError:
                self.fail(f"الرقم {number} أثار خطأ تحقق على الرغم من أنه صحيح")
    
    def test_invalid_positive_numbers(self):
        """اختبار أرقام غير موجبة أو غير صحيحة"""
        invalid_numbers = [
            0, -1, -10, -100, -0.1, -0.01, -0.001, -1.5, -10.5, -100.5,
        ]
        
        for number in invalid_numbers:
            with self.assertRaises(ValidationError, msg=f"الرقم {number} لم يثر خطأ تحقق على الرغم من أنه غير صحيح"):
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
            'document.pdf',
            'report.docx',
            'spreadsheet.xlsx',
            'presentation.pptx',
            'text.txt',
            'compressed.zip',
            'compressed.rar',
        ]
        
        for filename in valid_files:
            try:
                validate_file_extension(filename)
            except ValidationError:
                self.fail(f"اسم الملف {filename} أثار خطأ تحقق على الرغم من أنه صحيح")
    
    def test_invalid_file_extensions(self):
        """اختبار امتدادات ملفات غير صحيحة"""
        invalid_files = [
            'document.exe',
            'script.bat',
            'program.sh',
            'script.js',
            'code.php',
            'program.py',
        ]
        
        for filename in invalid_files:
            with self.assertRaises(ValidationError, msg=f"اسم الملف {filename} لم يثر خطأ تحقق على الرغم من أنه غير صحيح"):
                validate_file_extension(filename)
    
    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_file_extension('program.exe')
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
            'image.jpg',
            'photo.jpeg',
            'graphics.png',
            'icon.gif',
            'vector.svg',
        ]
        
        for filename in valid_images:
            try:
                validate_image_extension(filename)
            except ValidationError:
                self.fail(f"اسم الصورة {filename} أثار خطأ تحقق على الرغم من أنه صحيح")
    
    def test_invalid_image_extensions(self):
        """اختبار امتدادات صور غير صحيحة"""
        invalid_images = [
            'document.pdf',
            'report.docx',
            'spreadsheet.xlsx',
            'presentation.pptx',
            'text.txt',
            'compressed.zip',
        ]
        
        for filename in invalid_images:
            with self.assertRaises(ValidationError, msg=f"اسم الصورة {filename} لم يثر خطأ تحقق على الرغم من أنه غير صحيح"):
                validate_image_extension(filename)
    
    def test_error_message(self):
        """اختبار رسالة الخطأ"""
        try:
            validate_image_extension('document.pdf')
            self.fail("لم يتم إثارة خطأ التحقق على الرغم من أن امتداد الصورة غير مسموح")
        except ValidationError as e:
            self.assertIn("امتداد الصورة غير مسموح به", str(e)) 