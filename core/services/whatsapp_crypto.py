import base64
import hashlib
from django.conf import settings
from django.core.cache import cache
from cryptography.fernet import Fernet, InvalidToken

_KEY_CACHE = None


def _get_fernet_key() -> bytes:
    """
    اشتقاق مفتاح تشفير متين 32-byte بصيغة URL-safe base64 لـ Fernet
    يستخدم WHATSAPP_ENCRYPTION_KEY أو يشتق مفتاحاً حتمياً من SECRET_KEY كـ Fallback
    """
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE

    raw_key = getattr(settings, 'WHATSAPP_ENCRYPTION_KEY', None)
    if not raw_key:
        raw_key = getattr(settings, 'SECRET_KEY', 'mwheba-erp-whatsapp-fallback-key')

    # حساب SHA-256 hash للحصول على 32 بايت حتمية ثم ترميزها بـ urlsafe_b64encode
    digest = hashlib.sha256(raw_key.encode('utf-8')).digest()
    _KEY_CACHE = base64.urlsafe_b64encode(digest)
    return _KEY_CACHE


def encrypt_token(plain_text: str) -> str:
    """تشفير التوكن النصي باستخدام AES-128-CBC + HMAC-SHA256 عبر Fernet"""
    if not plain_text:
        return ""
    if not isinstance(plain_text, str):
        plain_text = str(plain_text)
    fernet = Fernet(_get_fernet_key())
    encrypted_bytes = fernet.encrypt(plain_text.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')


def decrypt_token(cipher_text: str) -> str:
    """فك تشفير التوكن المشفر مع دعم التراجع السلس إذا كان النص غير مشفر"""
    if not cipher_text:
        return ""
    if not isinstance(cipher_text, str):
        cipher_text = str(cipher_text)
    
    # إذا لم يبدأ بترميز Fernet القياسي gAAAAA، فقد يكون توكن قديم غير مشفر
    if not cipher_text.startswith('gAAAAA'):
        return cipher_text

    try:
        fernet = Fernet(_get_fernet_key())
        decrypted_bytes = fernet.decrypt(cipher_text.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except (InvalidToken, Exception):
        # في حال الفشل أو كان النص غير مشفر، إرجاع النص كما هو كـ Fallback آمن
        return cipher_text


def get_cached_decrypted_token(account_id: int, cipher_text: str) -> str:
    """جلب التوكن المفكوك من الكاش المؤقت في الذاكرة (5 دقائق) لتسريع الأداء"""
    if not cipher_text:
        return ""
    cache_key = f"core_whatsapp_decrypted_token_{account_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    decrypted = decrypt_token(cipher_text)
    if decrypted:
        cache.set(cache_key, decrypted, timeout=300)
    return decrypted


def invalidate_token_cache(account_id: int) -> None:
    """مسح التوكن المخزن مؤقتاً عند تعديل الحساب أو تغيير المفتاح"""
    if account_id:
        cache.delete(f"core_whatsapp_decrypted_token_{account_id}")


class WhatsAppCryptoService:
    """واجهة خدمية موحدة لعمليات التشفير وفك التشفير وإدارة كاش التوكنات"""
    encrypt_token = staticmethod(encrypt_token)
    decrypt_token = staticmethod(decrypt_token)
    get_cached_decrypted_token = staticmethod(get_cached_decrypted_token)
    invalidate_token_cache = staticmethod(invalidate_token_cache)

