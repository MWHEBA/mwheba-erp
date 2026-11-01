# -*- coding: utf-8 -*-
"""
Tests for BlueprintMediaService - WebP Thumbnail Generation (< 40KB)
MWHEBA ERP — Real Estate Wave 3 (Phase 9)
"""
import io
import base64
import pytest
from PIL import Image

from real_estate.services.blueprint_service import BlueprintMediaService


@pytest.fixture
def sample_large_rgb_image_bytes():
    """توليد صورة اختبارية كبيرة بدقة 1920x1080"""
    img = Image.new("RGB", (1920, 1080), color=(34, 139, 34))
    stream = io.BytesIO()
    img.save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def sample_rgba_image_bytes():
    """توليد صورة اختبارية بشفافية RGBA"""
    img = Image.new("RGBA", (800, 600), color=(255, 0, 0, 128))
    stream = io.BytesIO()
    img.save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.django_db
class TestBlueprintWebPThumbnailGeneration:
    """اختبارات توليد الصور المصغرة للمخططات الهندسية بصيغة WebP بحجم أقل من 40 كيلوبايت"""

    def test_generate_webp_thumbnail_from_raw_bytes(self, sample_large_rgb_image_bytes):
        """التحقق من ضغط صورة كبيرة بصيغة WebP بحجم أقل من 40 كيلوبايت"""
        thumb_bytes = BlueprintMediaService.generate_webp_thumbnail(sample_large_rgb_image_bytes)

        # التحقق من أن الحجم أقل من 40KB
        assert len(thumb_bytes) <= BlueprintMediaService.MAX_THUMBNAIL_BYTES
        assert len(thumb_bytes) <= 40 * 1024

        # التحقق من أن الناتج صيغة WebP صالحة للقراءة
        with Image.open(io.BytesIO(thumb_bytes)) as thumb_img:
            assert thumb_img.format == "WEBP"
            assert thumb_img.size[0] <= 400
            assert thumb_img.size[1] <= 400

    def test_generate_webp_thumbnail_from_bytesio_stream(self, sample_large_rgb_image_bytes):
        """التحقق من إمكانية تمرير كائن BytesIO مباشرة للمحرك"""
        stream = io.BytesIO(sample_large_rgb_image_bytes)
        thumb_bytes = BlueprintMediaService.generate_webp_thumbnail(stream)

        assert isinstance(thumb_bytes, bytes)
        assert len(thumb_bytes) <= 40 * 1024

        with Image.open(io.BytesIO(thumb_bytes)) as thumb_img:
            assert thumb_img.format == "WEBP"

    def test_generate_webp_thumbnail_preserves_aspect_ratio(self):
        """التحقق من الحفاظ الدقيق على نسبة العرض للارتفاع للأبعاد الهندسية"""
        # صورة بنسبة 2:1 (1600x800)
        img = Image.new("RGB", (1600, 800), color=(70, 130, 180))
        stream = io.BytesIO()
        img.save(stream, format="JPEG")

        thumb_bytes = BlueprintMediaService.generate_webp_thumbnail(
            stream.getvalue(),
            max_dimensions=(400, 400)
        )

        with Image.open(io.BytesIO(thumb_bytes)) as thumb_img:
            assert thumb_img.size == (400, 200)

    def test_generate_base64_webp_thumbnail(self, sample_large_rgb_image_bytes):
        """التحقق من توليد شفرة Base64 صالحة مع ترويسة data:image/webp;base64"""
        data_uri = BlueprintMediaService.generate_base64_webp_thumbnail(sample_large_rgb_image_bytes)

        assert isinstance(data_uri, str)
        assert data_uri.startswith("data:image/webp;base64,")

        # فك الشفرة والتأكد من فتح الصورة كـ WebP
        b64_payload = data_uri.replace("data:image/webp;base64,", "")
        decoded_bytes = base64.b64decode(b64_payload)
        with Image.open(io.BytesIO(decoded_bytes)) as img:
            assert img.format == "WEBP"

    def test_generate_webp_thumbnail_rgba_transparency_handling(self, sample_rgba_image_bytes):
        """التحقق من تحويل الصور ذات الشفافية RGBA دون تشويه أو خطأ برمجي"""
        thumb_bytes = BlueprintMediaService.generate_webp_thumbnail(sample_rgba_image_bytes)

        assert len(thumb_bytes) <= 40 * 1024
        with Image.open(io.BytesIO(thumb_bytes)) as thumb_img:
            assert thumb_img.format == "WEBP"
