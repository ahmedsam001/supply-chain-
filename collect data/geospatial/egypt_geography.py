"""
Egyptian Geography Normalizer

Normalizes location data into the Egyptian administrative hierarchy:
    Egypt → Governorate → City → District → Store/Zone

Uses an unambiguous reference database of Egyptian governorates and major cities.
Never guesses governorates: ambiguous or unverifiable inputs map to "unknown"
while preserving raw input text.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional


# ─── Egyptian Governorates ────────────────────────────────────────────

GOVERNORATES = {
    # Name: (Arabic name, capital city)
    "Cairo": ("القاهرة", "Cairo"),
    "Giza": ("الجيزة", "Giza"),
    "Alexandria": ("الإسكندرية", "Alexandria"),
    "Qalyubia": ("القليوبية", "Banha"),
    "Sharqia": ("الشرقية", "Zagazig"),
    "Dakahlia": ("الدقهلية", "Mansoura"),
    "Beheira": ("البحيرة", "Damanhour"),
    "Monufia": ("المنوفية", "Shibin El Kom"),
    "Gharbia": ("الغربية", "Tanta"),
    "Kafr El Sheikh": ("كفر الشيخ", "Kafr El Sheikh"),
    "Damietta": ("دمياط", "Damietta"),
    "Port Said": ("بورسعيد", "Port Said"),
    "Ismailia": ("الإسماعيلية", "Ismailia"),
    "Suez": ("السويس", "Suez"),
    "North Sinai": ("شمال سيناء", "Arish"),
    "South Sinai": ("جنوب سيناء", "El Tor"),
    "Fayoum": ("الفيوم", "Fayoum"),
    "Beni Suef": ("بني سويف", "Beni Suef"),
    "Minya": ("المنيا", "Minya"),
    "Asyut": ("أسيوط", "Asyut"),
    "Sohag": ("سوهاج", "Sohag"),
    "Qena": ("قنا", "Qena"),
    "Luxor": ("الأقصر", "Luxor"),
    "Aswan": ("أسوان", "Aswan"),
    "Red Sea": ("البحر الأحمر", "Hurghada"),
    "New Valley": ("الوادي الجديد", "Kharga"),
    "Matrouh": ("مطروح", "Marsa Matrouh"),
}

# Unambiguous cities mapped to their official governorate
# Audited for WP7:
# - Sheikh Zayed & 6th of October -> Giza (never Cairo)
# - Obour (El Obour City) -> Qalyubia (not Cairo)
# - 10th of Ramadan -> Sharqia
CITY_TO_GOVERNORATE = {
    # Cairo Governorate
    "Cairo": "Cairo", "Heliopolis": "Cairo", "Nasr City": "Cairo",
    "Maadi": "Cairo", "New Cairo": "Cairo", "Fifth Settlement": "Cairo",
    "First Settlement": "Cairo", "Katameya": "Cairo", "Shorouk": "Cairo",
    "El Shorouk": "Cairo", "Badr": "Cairo", "Mokattam": "Cairo",
    "Helwan": "Cairo", "Ain Shams": "Cairo", "Shubra": "Cairo",
    "Zamalek": "Cairo", "Downtown Cairo": "Cairo", "Garden City": "Cairo",
    "Madinaty": "Cairo", "Rehab": "Cairo", "El Rehab": "Cairo",
    "New Administrative Capital": "Cairo",
    "Alf Maskan": "Cairo", "Gesr Al Suez": "Cairo", "Sheraton": "Cairo",
    "Almaza": "Cairo", "Almazah": "Cairo", "Bab Al-Louq": "Cairo",
    "Abdeen": "Cairo", "El Basatin": "Cairo", "Shoubra": "Cairo",
    "El Moqattam": "Cairo",

    # Giza Governorate (never default to Cairo)
    "Giza": "Giza", "6th of October": "Giza", "6 October": "Giza",
    "Six of October": "Giza", "Sheikh Zayed": "Giza", "Zayed": "Giza",
    "Haram": "Giza", "Dokki": "Giza", "Mohandessin": "Giza",
    "Faisal": "Giza", "Agouza": "Giza", "Smart Village": "Giza",
    "Imbaba": "Giza", "Hadayek El Ahram": "Giza",
    "Ad Doqi": "Giza", "Mit Oqbah": "Giza", "El Talbia": "Giza",

    # Qalyubia Governorate
    "Banha": "Qalyubia", "Benha": "Qalyubia",
    "Obour": "Qalyubia", "El Obour": "Qalyubia",
    "Shubra El Kheima": "Qalyubia", "Qalyub": "Qalyubia",
    "Elobour": "Qalyubia", "El Obour City": "Qalyubia", "Obour City": "Qalyubia",

    # Alexandria Governorate
    "Alexandria": "Alexandria", "Smouha": "Alexandria",
    "San Stefano": "Alexandria", "Roshdy": "Alexandria",
    "Zezenia": "Alexandria", "Sidi Gaber": "Alexandria",
    "Miami": "Alexandria", "Mandara": "Alexandria",
    "Agami": "Alexandria", "Borg El Arab": "Alexandria",

    # Delta
    "Mansoura": "Dakahlia", "Tanta": "Gharbia",
    "El Mahalla El Kubra": "Gharbia", "Mahalla": "Gharbia",
    "Zagazig": "Sharqia", "10th of Ramadan": "Sharqia",
    "Damanhour": "Beheira", "Kafr El Sheikh": "Kafr El Sheikh",
    "Damietta": "Damietta", "New Damietta": "Damietta",
    "Shibin El Kom": "Monufia", "Sadat City": "Monufia",

    # Canal
    "Port Said": "Port Said", "Ismailia": "Ismailia",
    "Suez": "Suez", "Ain Sokhna": "Suez",

    # Upper Egypt
    "Fayoum": "Fayoum", "Beni Suef": "Beni Suef",
    "Minya": "Minya", "Asyut": "Asyut", "Assiut": "Asyut",
    "Sohag": "Sohag", "Qena": "Qena",
    "Luxor": "Luxor", "Aswan": "Aswan",

    # Red Sea / Sinai / Matrouh
    "Hurghada": "Red Sea", "El Gouna": "Red Sea", "Marsa Alam": "Red Sea",
    "Sharm El Sheikh": "South Sinai", "Dahab": "South Sinai", "El Tor": "South Sinai",
    "Arish": "North Sinai",
    "Marsa Matrouh": "Matrouh", "North Coast": "Matrouh", "El Alamein": "Matrouh", "New Alamein": "Matrouh",
    "Alamein": "Matrouh", "Alamien": "Matrouh",
}

# Arabic city/area names -> (canonical English city, canonical English governorate)
ARABIC_CITY_TO_GOVERNORATE: dict[str, tuple[str, str]] = {
    "القاهرة": ("Cairo", "Cairo"),
    "مدينة نصر": ("Nasr City", "Cairo"),
    "مصر الجديدة": ("Heliopolis", "Cairo"),
    "المعادي": ("Maadi", "Cairo"),
    "القاهرة الجديدة": ("New Cairo", "Cairo"),
    "التجمع الخامس": ("Fifth Settlement", "Cairo"),
    "الشروق": ("Shorouk", "Cairo"),
    "مدينتي": ("Madinaty", "Cairo"),
    "الرحاب": ("Rehab", "Cairo"),
    "المقطم": ("Mokattam", "Cairo"),
    "حلوان": ("Helwan", "Cairo"),
    "عين شمس": ("Ain Shams", "Cairo"),
    "الزمالك": ("Zamalek", "Cairo"),
    "العاصمة الإدارية": ("New Administrative Capital", "Cairo"),
    "الجيزة": ("Giza", "Giza"),
    "الشيخ زايد": ("Sheikh Zayed", "Giza"),
    "زايد": ("Sheikh Zayed", "Giza"),
    "السادس من أكتوبر": ("6th of October", "Giza"),
    "6 أكتوبر": ("6th of October", "Giza"),
    "٦ أكتوبر": ("6th of October", "Giza"),
    "الدقي": ("Dokki", "Giza"),
    "المهندسين": ("Mohandessin", "Giza"),
    "الهرم": ("Haram", "Giza"),
    "فيصل": ("Faisal", "Giza"),
    "العجوزة": ("Agouza", "Giza"),
    "القرية الذكية": ("Smart Village", "Giza"),
    "بنها": ("Banha", "Qalyubia"),
    "العبور": ("Obour", "Qalyubia"),
    "شبرا الخيمة": ("Shubra El Kheima", "Qalyubia"),
    "الإسكندرية": ("Alexandria", "Alexandria"),
    "الاسكندرية": ("Alexandria", "Alexandria"),
    "اسكندرية": ("Alexandria", "Alexandria"),
    "سموحة": ("Smouha", "Alexandria"),
    "سان ستيفانو": ("San Stefano", "Alexandria"),
    "سيدي جابر": ("Sidi Gaber", "Alexandria"),
    "ميامي": ("Miami", "Alexandria"),
    "العجمي": ("Agami", "Alexandria"),
    "المنصورة": ("Mansoura", "Dakahlia"),
    "طنطا": ("Tanta", "Gharbia"),
    "المحلة الكبرى": ("El Mahalla El Kubra", "Gharbia"),
    "الزقازيق": ("Zagazig", "Sharqia"),
    "العاشر من رمضان": ("10th of Ramadan", "Sharqia"),
    "دمنهور": ("Damanhour", "Beheira"),
    "كفر الشيخ": ("Kafr El Sheikh", "Kafr El Sheikh"),
    "دمياط": ("Damietta", "Damietta"),
    "شبين الكوم": ("Shibin El Kom", "Monufia"),
    "السادات": ("Sadat City", "Monufia"),
    "بورسعيد": ("Port Said", "Port Said"),
    "الإسماعيلية": ("Ismailia", "Ismailia"),
    "الاسماعيلية": ("Ismailia", "Ismailia"),
    "السويس": ("Suez", "Suez"),
    "العين السخنة": ("Ain Sokhna", "Suez"),
    "الفيوم": ("Fayoum", "Fayoum"),
    "بني سويف": ("Beni Suef", "Beni Suef"),
    "المنيا": ("Minya", "Minya"),
    "أسيوط": ("Asyut", "Asyut"),
    "اسيوط": ("Asyut", "Asyut"),
    "سوهاج": ("Sohag", "Sohag"),
    "قنا": ("Qena", "Qena"),
    "الأقصر": ("Luxor", "Luxor"),
    "الاقصر": ("Luxor", "Luxor"),
    "أسوان": ("Aswan", "Aswan"),
    "اسوان": ("Aswan", "Aswan"),
    "الغردقة": ("Hurghada", "Red Sea"),
    "الجونة": ("El Gouna", "Red Sea"),
    "شرم الشيخ": ("Sharm El Sheikh", "South Sinai"),
    "دهب": ("Dahab", "South Sinai"),
    "العريش": ("Arish", "North Sinai"),
    "مرسى مطروح": ("Marsa Matrouh", "Matrouh"),
    "الساحل الشمالي": ("North Coast", "Matrouh"),
}

# Ambiguous place names that exist in multiple governorates or cannot be
# mapped without additional context. Must resolve to "unknown".
AMBIGUOUS_PLACES = {
    "downtown", "وسط البلد", "el salam", "السلام", "el nozha", "النزهة",
    "industrial zone", "المنطقة الصناعية", "new city", "station",
}


def _normalize_arabic_text(text: str) -> str:
    """Normalize common Arabic letter variants (Alef forms, Teh Marbuta) for matching."""
    text = text.strip()
    text = re.sub(r"[أإآ]", "أ", text)
    return text


def normalize_governorate(text: str) -> Optional[str]:
    """
    Normalize a governorate name to its canonical English form.
    Handles common variations and Arabic names. Returns None if unverifiable.
    """
    if not text:
        return None

    text_clean = text.strip()
    if text_clean.lower() == "unknown":
        return "unknown"

    # Direct match
    if text_clean in GOVERNORATES:
        return text_clean

    # Case-insensitive match
    for gov in GOVERNORATES:
        if gov.lower() == text_clean.lower():
            return gov

    # Arabic governorate name match
    for gov, (arabic, _) in GOVERNORATES.items():
        if arabic in text_clean or _normalize_arabic_text(arabic) in _normalize_arabic_text(text_clean):
            return gov

    # Common variations
    variations = {
        "el cairo": "Cairo", "al qahira": "Cairo",
        "el giza": "Giza", "al gizah": "Giza",
        "al iskandariyya": "Alexandria", "alex": "Alexandria",
        "sharkia": "Sharqia", "daqahlia": "Dakahlia",
        "buhaira": "Beheira", "menoufia": "Monufia",
        "gharbiya": "Gharbia", "qalyubiya": "Qalyubia",
        "kaliobeya": "Qalyubia", "kalyobiya": "Qalyubia",
        "assiut": "Asyut", "fayyum": "Fayoum", "el fayoum": "Fayoum",
        "kafr el-sheikh": "Kafr El Sheikh", "port-said": "Port Said",
        "red-sea": "Red Sea", "north-sinai": "North Sinai", "south-sinai": "South Sinai",
        "new-valley": "New Valley", "beni-suef": "Beni Suef",
    }
    for var, gov in variations.items():
        if var in text_clean.lower():
            return gov

    return None


def city_to_governorate(city: str) -> Optional[str]:
    """
    Look up the governorate for a given city name (English or Arabic).
    Returns None if ambiguous or unknown — never guesses.
    """
    if not city:
        return None

    city_clean = city.strip()
    city_lower = city_clean.lower()

    if city_lower in AMBIGUOUS_PLACES:
        return None

    # Direct English match
    if city_clean in CITY_TO_GOVERNORATE:
        return CITY_TO_GOVERNORATE[city_clean]

    # Case-insensitive exact match
    for c, gov in CITY_TO_GOVERNORATE.items():
        if c.lower() == city_lower:
            return gov

    # Arabic exact & substring match (longest first)
    city_norm_ar = _normalize_arabic_text(city_clean)
    for ar_city, (_, gov) in sorted(
        ARABIC_CITY_TO_GOVERNORATE.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        if ar_city in city_clean or _normalize_arabic_text(ar_city) in city_norm_ar:
            return gov

    # Substring match in English (longest match first, e.g. "First Al Sheikh Zayed" -> "Sheikh Zayed" -> "Giza")
    for c, gov in sorted(CITY_TO_GOVERNORATE.items(), key=lambda kv: len(kv[0]), reverse=True):
        if c.lower() in city_lower:
            return gov

    # Fallback: check if city is actually a governorate name (e.g. "Qalyubia" or "القاهرة")
    gov_match = normalize_governorate(city_clean)
    if gov_match and gov_match != "unknown":
        return gov_match

    return None


def normalize_location(
    address: Optional[str] = None,
    city: Optional[str] = None,
    governorate: Optional[str] = None,
    district: Optional[str] = None,
) -> dict:
    """
    Normalize location fields without guessing.

    - Preserves raw inputs (`raw_address`, `raw_city`, `raw_governorate`).
    - Never fabricates `district` unless explicitly passed by the source.
    - Maps ambiguous or unverifiable places to `governorate="unknown"` when
      location text was provided but could not be verified.
    """
    has_input = any(bool(x and str(x).strip()) for x in (address, city, governorate))

    resolved_city: Optional[str] = city.strip() if city and city.strip() else None
    resolved_gov: Optional[str] = None

    # 1. Explicit governorate if provided
    if governorate and governorate.strip():
        resolved_gov = normalize_governorate(governorate)

    # 2. Resolve from city (English or Arabic)
    if resolved_city:
        if resolved_city.lower() in AMBIGUOUS_PLACES:
            resolved_gov = None
        else:
            # Check Arabic city dictionary to also normalize city name
            city_norm_ar = _normalize_arabic_text(resolved_city)
            for ar_name, (en_city, en_gov) in sorted(
                ARABIC_CITY_TO_GOVERNORATE.items(), key=lambda kv: len(kv[0]), reverse=True
            ):
                if ar_name in resolved_city or _normalize_arabic_text(ar_name) in city_norm_ar:
                    resolved_city = en_city
                    if not resolved_gov:
                        resolved_gov = en_gov
                    break
            if not resolved_gov:
                resolved_gov = city_to_governorate(resolved_city)

    # 3. Extract from address if city/governorate still missing
    if address and address.strip():
        addr_clean = address.strip()
        addr_lower = addr_clean.lower()
        addr_norm_ar = _normalize_arabic_text(addr_clean)

        # Check explicit "<Name> Governorate" in address unless a satellite city overrides
        _satellite_overrides = ("6th of october", "6 october", "sheikh zayed", "zayed", "obour", "elobour", "10th of ramadan", "alamein", "alamien", "north coast")
        if not resolved_gov and not any(k in addr_lower for k in _satellite_overrides):
            gov_explicit = re.search(r"\b(Cairo|Giza|Alexandria|Qalyubia|Sharqia|Dakahlia|Beheira|Monufia|Gharbia|Damietta|Port Said|Ismailia|Suez|Fayoum|Faiyum|Beni Suef|Minya|Asyut|Assiut|Sohag|Qena|Luxor|Aswan|Red Sea|Matrouh)\s+Governorate\b", addr_clean, re.I)
            if gov_explicit:
                resolved_gov = normalize_governorate(gov_explicit.group(1))

        # Check English cities in address (longest first)
        if not resolved_city or not resolved_gov:
            for c, gov in sorted(CITY_TO_GOVERNORATE.items(), key=lambda kv: len(kv[0]), reverse=True):
                if c.lower() in addr_lower:
                    if not resolved_city:
                        resolved_city = c
                    if not resolved_gov:
                        resolved_gov = gov
                    break

        # Check Arabic cities in address (longest first)
        if not resolved_city or not resolved_gov:
            for ar_name, (en_city, en_gov) in sorted(
                ARABIC_CITY_TO_GOVERNORATE.items(), key=lambda kv: len(kv[0]), reverse=True
            ):
                if ar_name in addr_clean or _normalize_arabic_text(ar_name) in addr_norm_ar:
                    if not resolved_city:
                        resolved_city = en_city
                    if not resolved_gov:
                        resolved_gov = en_gov
                    break

        # Check governorate names in address
        if not resolved_gov:
            gov_from_addr = normalize_governorate(addr_clean)
            if gov_from_addr:
                resolved_gov = gov_from_addr

    # 4. If input was provided but governorate is still unverifiable -> "unknown"
    if has_input and not resolved_gov:
        resolved_gov = "unknown"

    return {
        "country": "Egypt",
        "city": resolved_city,
        "governorate": resolved_gov,
        "district": district.strip() if district and district.strip() else None,
        "raw_city": city,
        "raw_address": address,
        "raw_governorate": governorate,
    }


def derive_location_id(
    source_id: str,
    location_type: str,
    normalized_name: Optional[str] = None,
    address: Optional[str] = None,
) -> str:
    """
    Derive a deterministic, stable location_id from:
        source_id + location_type + normalized_name + address hash

    Ensures duplicate locations and name inconsistencies are detectable across runs.
    """
    def _clean(val: Optional[str]) -> str:
        if not val:
            return ""
        # Lowercase, collapse whitespace, strip punctuation variations
        s = str(val).strip().lower()
        s = re.sub(r"\s+", " ", s)
        return s

    src = _clean(source_id)
    ltype = _clean(location_type.value if hasattr(location_type, "value") else str(location_type))
    name = _clean(normalized_name)
    addr = _clean(address)
    addr_hash = hashlib.sha256(addr.encode("utf-8")).hexdigest()[:12] if addr else "noaddr"

    payload = f"{src}|{ltype}|{name}|{addr_hash}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"loc_{src}_{digest}"
