from django.test import TestCase
from django.core.exceptions import ValidationError
from core.validators import (
    validate_phone_number,
    validate_positive_number,
    validate_future_date,
    validate_file_extension,
    validate_file_size,
    validate_image_dimensions
)
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
import datetime
from PIL import Image
import io
import os


class PhoneNumberValidatorTest(TestCase):
    """
    اختبارات متحقق أرقام الهاتف
    """
    
    def test_valid_phone_numbers(self):
        """
        اختبار أرقام هاتف صحيحة
        """
        valid_numbers = [
            '+201234567890',
            '01234567890',
            '+966512345678',
            '0512345678',
            '+1234567890123'
        ]
        
        for number in valid_numbers:
            try:
                validate_phone_number(number)
            except ValidationError:
                self.fail(f"رفض رقم هاتف صحيح: {number}")
    
    def test_invalid_phone_numbers(self):
        """
        اختبار أرقام هاتف غير صحيحة
        """
        invalid_numbers = [
            'abc123456789',  # يحتوي على أحرف
            '123',  # قصير جدًا
            '+1234567890123456789',  # طويل جدًا
            '١٢٣٤٥٦٧٨٩٠',  # أرقام عربية
            '+12-345-678-90'  # يحتوي على علامات ترقيم
        ]
        
        for number in invalid_numbers:
            with self.assertRaises(ValidationError):
                validate_phone_number(number)
    
    def test_empty_phone_number(self):
        """
        اختبار رقم هاتف فارغ
        """
        with self.assertRaises(ValidationError):
            validate_phone_number("")


class PositiveNumberValidatorTest(TestCase):
    """
    اختبارات متحقق الأرقام الموجبة
    """
    
    def test_valid_positive_numbers(self):
        """
        اختبار أرقام موجبة صحيحة
        """
        valid_numbers = [1, 10, 100, 0.1, 0.01, 1000.5]
        
        for number in valid_numbers:
            try:
                validate_positive_number(number)
            except ValidationError:
                self.fail(f"رفض رقم موجب صحيح: {number}")
    
    def test_invalid_positive_numbers(self):
        """
        اختبار أرقام غير موجبة
        """
        invalid_numbers = [0, -1, -10, -0.1]
        
        for number in invalid_numbers:
            with self.assertRaises(ValidationError):
                validate_positive_number(number)
    
    def test_non_number_input(self):
        """
        اختبار إدخال ليس رقمًا
        """
        with self.assertRaises(ValidationError):
            validate_positive_number("abc")


class FutureDateValidatorTest(TestCase):
    """
    اختبارات متحقق التواريخ المستقبلية
    """
    
    def test_valid_future_dates(self):
        """
        اختبار تواريخ مستقبلية صحيحة
        """
        today = timezone.now().date()
        valid_dates = [
            today + datetime.timedelta(days=1),
            today + datetime.timedelta(days=7),
            today + datetime.timedelta(days=30),
            today + datetime.timedelta(days=365)
        ]
        
        for date in valid_dates:
            try:
                validate_future_date(date)
            except ValidationError:
                self.fail(f"رفض تاريخ مستقبلي صحيح: {date}")
    
    def test_invalid_future_dates(self):
        """
        اختبار تواريخ غير مستقبلية
        """
        today = timezone.now().date()
        invalid_dates = [
            today,
            today - datetime.timedelta(days=1),
            today - datetime.timedelta(days=7),
            today - datetime.timedelta(days=30)
        ]
        
        for date in invalid_dates:
            with self.assertRaises(ValidationError):
                validate_future_date(date)
    
    def test_future_date_with_include_today(self):
        """
        اختبار تواريخ مستقبلية مع تضمين اليوم الحالي
        """
        today = timezone.now().date()
        
        # اليوم الحالي يجب أن يكون صحيحًا مع include_today=True
        try:
            validate_future_date(today, include_today=True)
        except ValidationError:
            self.fail(f"رفض تاريخ اليوم مع include_today=True: {today}")
        
        # اليوم الحالي يجب أن يكون غير صحيح مع include_today=False
        with self.assertRaises(ValidationError):
            validate_future_date(today, include_today=False)


class FileExtensionValidatorTest(TestCase):
    """
    اختبارات متحقق امتدادات الملفات
    """
    
    def test_valid_file_extensions(self):
        """
        اختبار ملفات بامتدادات صحيحة
        """
        # إنشاء ملفات اختبار وهمية
        pdf_file = SimpleUploadedFile("test.pdf", b"file content", content_type="application/pdf")
        doc_file = SimpleUploadedFile("test.doc", b"file content", content_type="application/msword")
        docx_file = SimpleUploadedFile("test.docx", b"file content", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        jpg_file = SimpleUploadedFile("test.jpg", b"file content", content_type="image/jpeg")
        png_file = SimpleUploadedFile("test.png", b"file content", content_type="image/png")
        
        # اختبار كل ملف مع الامتدادات المناسبة
        try:
            validate_file_extension(pdf_file, ['pdf'])
            validate_file_extension(doc_file, ['doc', 'docx'])
            validate_file_extension(docx_file, ['doc', 'docx'])
            validate_file_extension(jpg_file, ['jpg', 'jpeg', 'png'])
            validate_file_extension(png_file, ['jpg', 'jpeg', 'png'])
        except ValidationError:
            self.fail("رفض ملف بامتداد صحيح")
    
    def test_invalid_file_extensions(self):
        """
        اختبار ملفات بامتدادات غير صحيحة
        """
        # إنشاء ملفات اختبار وهمية
        pdf_file = SimpleUploadedFile("test.pdf", b"file content", content_type="application/pdf")
        exe_file = SimpleUploadedFile("test.exe", b"file content", content_type="application/x-msdownload")
        
        # اختبار رفض امتدادات غير صحيحة
        with self.assertRaises(ValidationError):
            validate_file_extension(pdf_file, ['doc', 'docx'])
        
        with self.assertRaises(ValidationError):
            validate_file_extension(exe_file, ['pdf', 'doc', 'docx'])
    
    def test_empty_allowed_extensions(self):
        """
        اختبار قائمة امتدادات فارغة
        """
        pdf_file = SimpleUploadedFile("test.pdf", b"file content", content_type="application/pdf")
        
        with self.assertRaises(ValidationError):
            validate_file_extension(pdf_file, [])


class FileSizeValidatorTest(TestCase):
    """
    اختبارات متحقق حجم الملفات
    """
    
    def test_valid_file_sizes(self):
        """
        اختبار ملفات بأحجام صحيحة
        """
        # إنشاء ملف صغير
        small_file = SimpleUploadedFile("test.txt", b"Small file content")
        
        # تحديد أحجام مختلفة للاختبار
        sizes = [
            1024,  # 1 كيلوبايت
            1024 * 1024,  # 1 ميجابايت
            5 * 1024 * 1024  # 5 ميجابايت
        ]
        
        # اختبار الملف مع أحجام مختلفة
        for size in sizes:
            try:
                validate_file_size(small_file, max_size=size)
            except ValidationError:
                self.fail(f"رفض ملف بحجم أقل من الحجم الأقصى: {size}")
    
    def test_invalid_file_sizes(self):
        """
        اختبار ملفات بأحجام غير صحيحة
        """
        # إنشاء ملف كبير
        large_file_content = b"x" * 1024 * 100  # 100 كيلوبايت
        large_file = SimpleUploadedFile("large.txt", large_file_content)
        
        # اختبار رفض الملف الكبير
        with self.assertRaises(ValidationError):
            validate_file_size(large_file, max_size=1024 * 10)  # 10 كيلوبايت


class ImageDimensionsValidatorTest(TestCase):
    """
    اختبارات متحقق أبعاد الصورة
    """
    
    def setUp(self):
        """
        إعداد ملفات الصور للاختبارات
        """
        # إنشاء صورة بأبعاد محددة
        self.create_test_image(100, 100, 'small_square.png')
        self.create_test_image(800, 600, 'medium_rectangle.png')
        self.create_test_image(1200, 800, 'large_rectangle.png')
    
    def create_test_image(self, width, height, filename):
        """
        إنشاء صورة اختبار بأبعاد محددة
        """
        image = Image.new('RGB', (width, height), color='red')
        image_io = io.BytesIO()
        image.save(image_io, format='PNG')
        image_io.seek(0)
        
        setattr(self, filename.replace('.', '_'), SimpleUploadedFile(
            filename,
            image_io.read(),
            content_type='image/png'
        ))
    
    def tearDown(self):
        """
        تنظيف بعد الاختبارات
        """
        # حذف ملفات الصور المؤقتة إذا تم إنشاؤها في نظام الملفات
        pass
    
    def test_valid_image_dimensions(self):
        """
        اختبار صور بأبعاد صحيحة
        """
        try:
            # صورة صغيرة تلبي الحد الأدنى
            validate_image_dimensions(self.small_square_png, min_width=50, min_height=50)
            
            # صورة متوسطة تلبي حدود النسبة
            validate_image_dimensions(self.medium_rectangle_png, min_width=800, min_height=600)
            
            # صورة كبيرة أقل من الحد الأقصى
            validate_image_dimensions(self.large_rectangle_png, max_width=2000, max_height=1500)
        except ValidationError:
            self.fail("رفض صورة بأبعاد صحيحة")
    
    def test_invalid_image_dimensions(self):
        """
        اختبار صور بأبعاد غير صحيحة
        """
        # صورة أصغر من الحد الأدنى
        with self.assertRaises(ValidationError):
            validate_image_dimensions(self.small_square_png, min_width=200, min_height=200)
        
        # صورة أكبر من الحد الأقصى
        with self.assertRaises(ValidationError):
            validate_image_dimensions(self.large_rectangle_png, max_width=1000, max_height=600)
    
    def test_image_aspect_ratio(self):
        """
        اختبار نسبة أبعاد الصورة
        """
        # نسبة أبعاد صحيحة
        try:
            validate_image_dimensions(self.medium_rectangle_png, aspect_ratio=4/3)
        except ValidationError:
            self.fail("رفض صورة بنسبة أبعاد صحيحة")
        
        # نسبة أبعاد غير صحيحة
        with self.assertRaises(ValidationError):
            validate_image_dimensions(self.medium_rectangle_png, aspect_ratio=1/1)
    
    def test_non_image_file(self):
        """
        اختبار ملف ليس بصورة
        """
        text_file = SimpleUploadedFile("test.txt", b"Not an image", content_type="text/plain")
        
        with self.assertRaises(ValidationError):
            validate_image_dimensions(text_file)
    
    def test_corrupt_image_file(self):
        """
        اختبار ملف صورة تالف
        """
        corrupt_image = SimpleUploadedFile("corrupt.png", b"Corrupt image data", content_type="image/png")
        
        with self.assertRaises(ValidationError):
            validate_image_dimensions(corrupt_image) 