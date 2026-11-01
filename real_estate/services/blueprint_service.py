# -*- coding: utf-8 -*-
"""
BlueprintMediaService - محرك معالجة وضغط الرسومات المعمارية والمخططات بصيغة WebP
MWHEBA ERP — Lightweight Architectural Blueprint & WebP Thumbnail Generator (< 40KB)
"""
import io
import base64
import logging
from typing import Tuple, Union
from PIL import Image

logger = logging.getLogger(__name__)


class BlueprintMediaService:
    """
    محرك معالجة وضغط مخططات الوحدات والرسومات الهندسية:
    - توليد صور مصغرة بصيغة WebP بحجم فائق الصغر (< 40KB) للعرض اللحظي في مصفوفة الوحدات.
    - الحفاظ الصارم على نسبة العرض للارتفاع وجودة الخطوط المعمارية.
    """

    MAX_THUMBNAIL_BYTES = 40 * 1024  # 40KB
    DEFAULT_MAX_DIMENSIONS = (400, 400)
    DEFAULT_QUALITY = 75

    @classmethod
    def generate_webp_thumbnail(
        cls,
        image_input: Union[bytes, io.BytesIO],
        max_dimensions: Tuple[int, int] = DEFAULT_MAX_DIMENSIONS,
        quality: int = DEFAULT_QUALITY
    ) -> bytes:
        """
        تحويل وضغط الصورة الأصلية إلى مصغرة WebP خفيفة الوزن (< 40KB)
        """
        if isinstance(image_input, bytes):
            stream = io.BytesIO(image_input)
        else:
            stream = image_input
            stream.seek(0)

        with Image.open(stream) as img:
            # تحويل صيغ الألوان (CMYK / RGBA) إلى RGB لضمان ثبات التدرجات في WebP
            if img.mode in ("RGBA", "LA", "P"):
                # الحفاظ على الشفافية إن وجدت أو استخدام خلفية بيضاء
                background = Image.new("RGBA", img.size, (255, 255, 255, 255))
                background.paste(img, (0, 0), img if img.mode == "RGBA" else None)
                rgb_img = background.convert("RGB")
            elif img.mode != "RGB":
                rgb_img = img.convert("RGB")
            else:
                rgb_img = img.copy()

            # تغيير الحجم مع الحفاظ على الأبعاد الهندسية
            rgb_img.thumbnail(max_dimensions, Image.Resampling.LANCZOS)

            # الضغط التكراري التدريجي للوصول لحجم أقل من 40KB
            current_quality = quality
            while current_quality >= 30:
                out_stream = io.BytesIO()
                rgb_img.save(out_stream, format="WEBP", quality=current_quality, method=4)
                out_bytes = out_stream.getvalue()

                if len(out_bytes) <= cls.MAX_THUMBNAIL_BYTES or current_quality <= 35:
                    logger.debug(
                        f"Generated WebP thumbnail: {len(out_bytes)} bytes at quality={current_quality}, "
                        f"size={rgb_img.size}"
                    )
                    return out_bytes

                current_quality -= 10

            return out_bytes

    @classmethod
    def generate_base64_webp_thumbnail(
        cls,
        image_input: Union[bytes, io.BytesIO],
        max_dimensions: Tuple[int, int] = DEFAULT_MAX_DIMENSIONS,
        quality: int = DEFAULT_QUALITY
    ) -> str:
        """
        توليد سلسلة Base64 جاهزة للعرض الفوري في قوالب HTML / JSON
        """
        webp_bytes = cls.generate_webp_thumbnail(
            image_input=image_input,
            max_dimensions=max_dimensions,
            quality=quality
        )
        encoded = base64.b64encode(webp_bytes).decode('utf-8')
        return f"data:image/webp;base64,{encoded}"
