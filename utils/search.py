"""
MWHEBA ERP - Unified Smart Arabic Search Engine
===============================================
A high-performance, database-agnostic Arabic search engine for Django ORM.
Handles:
  - Eastern/Western Arabic digits (٠-٩ -> 0-9)
  - Loanword/Persian characters (ڤ->ف, پ->ب, چ->ج, گ/ک->ك, ی->ي)
  - Diacritics (Tashkeel) and Tatweel stripping
  - Orthographic normalization (Alifs, Ta Marbuta, Alif Maqsura, Hamzas)
  - Definite article handling ("ال" prefix)
  - Conjunction prefix handling ("و" prefix)
  - Compound names normalization (عبد الرحمن <-> عبدالرحمن)
  - Multi-token AND logic across fields with OR variants
  - Code/phone/barcode fast bypass and separator normalization
"""

import re
from typing import List, Optional, Set
from django.db.models import Q, QuerySet

# -------------------------------------------------------------------
# Character Mapping Tables
# -------------------------------------------------------------------

EASTERN_TO_WESTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

ARABIC_DIACRITICS_REGEX = re.compile(
    r"[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]"
)

# Persian / Urdu / Loanword character replacements
FOREIGN_CHARS_TABLE = str.maketrans({
    "ڤ": "ف",
    "پ": "ب",
    "چ": "ج",
    "گ": "ك",
    "ک": "ك",
    "ی": "ي",
})

# Punctuation & symbols to replace with whitespace
PUNCTUATION_REGEX = re.compile(r"[\.,_\-\/\\()\[\]{}\"\':;?!+=*&^%$#@~`|<>،؛؟]")

# Compound name prefixes
COMPOUND_PREFIXES = ("عبد", "ابو", "كفر", "بور", "راس", "عين", "بني", "بيت", "دير")


def normalize_arabic(text: str) -> str:
    """
    Normalizes an Arabic/mixed string into canonical base form.
    
    Examples:
      - "مُؤَسَّسَةُ الأُفُقِ" -> "موسسه الافق"
      - "٠١٠١٢٣٤٥٦٧٨" -> "01012345678"
      - "شركة ڤودافون (ش.م.م)" -> "شركه فودافون ش م م"
      - "عبد الرحمن" -> "عبدالرحمن" (for token comparisons)
    """
    if not text:
        return ""

    # 1. Convert to string, lowercase English, and map digits
    s = str(text).lower().translate(EASTERN_TO_WESTERN_DIGITS)

    # 2. Map Persian / Loanword characters
    s = s.translate(FOREIGN_CHARS_TABLE)

    # 3. Strip Tashkeel (Diacritics) & Tatweel
    s = ARABIC_DIACRITICS_REGEX.sub("", s)

    # 4. Standardize Alif variants (أ, إ, آ, ٱ) -> ا
    s = re.sub(r"[أإآٱ]", "ا", s)

    # 5. Standardize Ta Marbuta (ة) -> ه
    s = s.replace("ة", "ه")

    # 6. Standardize Alif Maqsura (ى) and Hamza on Nabrah (ئ) -> ي
    s = re.sub(r"[ىئ]", "ي", s)

    # 7. Standardize Hamza on Waw (ؤ) -> و
    s = s.replace("ؤ", "و")

    # 8. Remove isolated Hamza (ء)
    s = s.replace("ء", "")

    # 9. Clean up excessive consecutive repeated characters (e.g. أفففق -> افق)
    s = re.sub(r"(.)\1{2,}", r"\1", s)

    # 10. Replace punctuations with space and collapse multiple spaces
    s = PUNCTUATION_REGEX.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()

    return s


def get_canonical_variants(token: str) -> List[str]:
    """
    Generates a targeted set of canonical search variants for a single token.
    Handles:
      - "ال" prefix addition/removal
      - Hamza on Alif ("أ"/"إ"/"آ" <-> "ا")
      - Hamza on Waw ("ؤ" <-> "و")
      - Loanword/foreign characters ("ف" <-> "ڤ", "ب" <-> "پ", "ج" <-> "چ", "ك" <-> "گ"/"ک")
      - Double-to-single consonant reduction (e.g. "مؤسسة" <-> "مؤسة")
      - Compound names (e.g. "عبد الرحمن" <-> "عبدالرحمن")
      - Conjunction "و" removal
    """
    if not token:
        return []

    clean_token = token.strip()
    norm_token = normalize_arabic(clean_token)

    variants: Set[str] = set()

    if clean_token:
        variants.add(clean_token)
    if norm_token:
        variants.add(norm_token)

    base = norm_token or clean_token

    # 1. Handle "ال" prefix
    if base.startswith("ال") and len(base) > 3:
        without_al = base[2:]
        variants.add(without_al)
        if without_al.startswith("ا"):
            variants.add(f"أ{without_al[1:]}")
            variants.add(f"الأ{without_al[1:]}")
    else:
        with_al = f"ال{base}"
        variants.add(with_al)
        if base.startswith("ا"):
            variants.add(f"أ{base[1:]}")
            variants.add(f"الأ{base[1:]}")

    # 2. Handle leading "و" (conjunction) if word is long enough (> 4 chars)
    if base.startswith("و") and len(base) > 4:
        without_waw = base[1:]
        variants.add(without_waw)
        if without_waw.startswith("ال") and len(without_waw) > 3:
            variants.add(without_waw[2:])

    # 3. Handle double-to-single consonant reduction (e.g. مؤسسة <-> مؤسة)
    single_consonant = re.sub(r"(.)\1+", r"\1", base)
    if single_consonant != base:
        variants.add(single_consonant)
        if "و" in single_consonant:
            variants.add(single_consonant.replace("و", "ؤ", 1))

    # 4. Handle Hamza on Waw ("و" <-> "ؤ") (e.g. موسسه -> مؤسسة, مؤسة)
    if "و" in base:
        w_to_hamza = base.replace("و", "ؤ", 1)
        variants.add(w_to_hamza)
        variants.add(re.sub(r"(.)\1+", r"\1", w_to_hamza))
    if "ؤ" in clean_token:
        variants.add(clean_token.replace("ؤ", "و", 1))

    # 5. Handle Reverse Loanwords ("ف" <-> "ڤ", "ب" <-> "پ", "ج" <-> "چ", "ك" <-> "گ")
    if "ف" in base:
        variants.add(base.replace("ف", "ڤ", 1))
    if "ب" in base:
        variants.add(base.replace("ب", "پ", 1))
    if "ج" in base:
        variants.add(base.replace("ج", "چ", 1))
    if "ك" in base:
        variants.add(base.replace("ك", "گ", 1))
    # 6. Handle compound names (e.g., عبد الرحمن <-> عبدالرحمن)
    for prefix in COMPOUND_PREFIXES:
        if base.startswith(prefix) and len(base) > len(prefix):
            rest = base[len(prefix):].strip()
            if rest:
                variants.add(f"{prefix} {rest}")
                variants.add(f"{prefix}{rest}")

    # 7. Handle Ta Marbuta / Ha and Ya / Alif Maqsura endings for all variants
    dual_endings: Set[str] = set()
    for v in variants:
        if v.endswith("ه"):
            dual_endings.add(v[:-1] + "ة")
        elif v.endswith("ة"):
            dual_endings.add(v[:-1] + "ه")
        if v.endswith("ي"):
            dual_endings.add(v[:-1] + "ى")
        elif v.endswith("ى"):
            dual_endings.add(v[:-1] + "ي")
    variants.update(dual_endings)

    return list(variants)[:24]


def build_smart_search_query(
    search_text: str,
    text_fields: List[str],
    code_fields: Optional[List[str]] = None,
) -> Q:
    """
    Constructs an optimized, database-agnostic Q object matching all tokens.
    
    Args:
      search_text: The user input search string.
      text_fields: List of model field paths for full text matching (e.g. ['name', 'company_name']).
      code_fields: List of model field paths for direct code/number matching (e.g. ['code', 'phone']).
      
    Returns:
      A composite django.db.models.Q object.
    """
    if not search_text or not search_text.strip():
        return Q()

    raw_query = search_text.strip()
    code_fields = code_fields or []

    # Check if the search text is purely digits or alphanumeric code (like a phone number or SKU)
    is_numeric_or_code = bool(re.match(r"^[0-9٠-٩\-_/\\A-Za-z]+$", raw_query))

    if is_numeric_or_code:
        # Fast path: direct match on code/phone fields with normalized digits
        clean_code = raw_query.translate(EASTERN_TO_WESTERN_DIGITS)
        code_q = Q()

        # Add code/number fields
        for field in code_fields:
            code_q |= Q(**{f"{field}__icontains": clean_code})
            # Also support stripped separators (e.g. INV2026001 from INV-2026-001)
            stripped_code = re.sub(r"[\s\-_/\\]", "", clean_code)
            if stripped_code and stripped_code != clean_code:
                code_q |= Q(**{f"{field}__icontains": stripped_code})

        # Also search in primary text fields in case code is part of name
        for field in text_fields[:2]:
            code_q |= Q(**{f"{field}__icontains": clean_code})

        return code_q

    # Text Search Path: Tokenize search string
    # Clean punctuations into spaces to isolate words
    cleaned_text = PUNCTUATION_REGEX.sub(" ", raw_query)
    raw_tokens = [t for t in cleaned_text.split() if t]

    if not raw_tokens:
        return Q()

    # Build composite AND query: all tokens must be matched
    combined_query = Q()

    for token in raw_tokens:
        token_variants = get_canonical_variants(token)
        token_q = Q()

        # Search all variants in text fields
        for field in text_fields:
            for variant in token_variants:
                token_q |= Q(**{f"{field}__icontains": variant})

        # Also search original token in code fields if any
        for field in code_fields:
            token_q |= Q(**{f"{field}__icontains": token})

        # Intersect with other tokens (AND logic)
        combined_query &= token_q

    return combined_query


def smart_search_filter(
    queryset: QuerySet,
    search_text: str,
    text_fields: List[str],
    code_fields: Optional[List[str]] = None,
    distinct: bool = False,
) -> QuerySet:
    """
    Applies the unified smart search query to a Django QuerySet.
    Automatically handles `.distinct()` if joins/nested fields are detected.
    
    Args:
      queryset: The initial QuerySet.
      search_text: The search query string from request.GET.
      text_fields: Text fields to search.
      code_fields: Code/Numeric fields to search.
      distinct: Force distinct on the resulting QuerySet.
      
    Returns:
      Filtered QuerySet.
    """
    if not search_text or not search_text.strip():
        return queryset

    query = build_smart_search_query(search_text, text_fields, code_fields)
    qs = queryset.filter(query)

    # Check if any field path is nested (contains '__') or explicit distinct requested
    has_nested_relations = any("__" in f for f in text_fields + (code_fields or []))
    if distinct or has_nested_relations:
        qs = qs.distinct()

    return qs
