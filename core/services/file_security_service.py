import hashlib
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class FileSecurityValidator:
    """
    خدمة الفحص الأمني للبايتات الحقيقية والتشفير وتطبيق قواعد الضغط السياقي (FileSecurityValidator)
    """

    BLOCKED_MAGIC_BYTES = [
        b'MZ',  # Windows Executable (.exe, .dll)
        b'\x7fELF',  # Linux Executable
        b'PK\x03\x04\x14\x00\x08\x00',  # Suspicious executable script inside zip
    ]

    @classmethod
    def validate_file_security(cls, uploaded_file) -> str:
        """
        فحص البايتات الحقيقية للبناء الرقمي للملف (Magic Bytes) واحتساب بصمة SHA-256
        """
        uploaded_file.seek(0)
        first_bytes = uploaded_file.read(4)

        for magic in cls.BLOCKED_MAGIC_BYTES:
            if first_bytes.startswith(magic):
                raise ValidationError(_("حظر أمني: تم اكتشاف ملف تنفيذي ضار ملغوم (Executable/MZ Signature)."))

        # احتساب بصمة SHA-256
        uploaded_file.seek(0)
        hasher = hashlib.sha256()
        for chunk in uploaded_file.chunks():
            hasher.update(chunk)

        uploaded_file.seek(0)
        return hasher.hexdigest()

    @staticmethod
    def verify_file_integrity(file_path: str, expected_hash: str) -> bool:
        """
        التحقق من سلامة البصمة الرقمية للملف عند التنزيل
        """
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest() == expected_hash
