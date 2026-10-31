"""
Canonical Department & Category Taxonomy for Egypt E-Commerce & Supply Chain Platform.

Organizes all products across all sources (Jumia, 2B, Carrefour, Tradeline, Dream2000, Raya, etc.)
into isolated, standardized departments (الأقسام الرئيسية) and categories (الفئات الفرعية):
- Mobiles & Tablets (الموبايلات والتابلت)
- Computing & IT (اللابتوب والكمبيوتر)
- Electronics & TVs (الإلكترونيات والشاشات)
- Home Appliances (الأجهزة المنزلية والكهربائية)
- Fresh Meats, Poultry & Seafood (اللحوم والدواجن والأسماك)
- Dairy, Cheese & Eggs (الألبان والجبن والبيض)
- Fruits & Vegetables (الخضروات والفواكه)
- Grocery & Pantry (البقالة والسلع الغذائية الجافة)
- Beverages (المشروبات والعصائر والشاي والقهوة)
- Bakery & Snacks (المخبوزات والحلويات والسناكس)
- Frozen Foods (المجمدات)
- Household & Cleaning (المنظفات والورقيات ومستلزمات المنزل)
- Personal Care & Beauty (العناية الشخصية والجمال)
- Other & General Merchandise (أخرى ومستلزمات متنوعة)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class Department(str, Enum):
    MOBILES_TABLETS = "mobiles_tablets"
    COMPUTING = "computing"
    ELECTRONICS_TV = "electronics_tv"
    HOME_APPLIANCES = "home_appliances"
    FRESH_MEATS_POULTRY = "fresh_meats_poultry"
    DAIRY_CHEESE_EGGS = "dairy_cheese_eggs"
    FRUITS_VEGETABLES = "fruits_vegetables"
    GROCERY_PANTRY = "grocery_pantry"
    BEVERAGES = "beverages"
    BAKERY_SNACKS = "bakery_snacks"
    FROZEN_FOODS = "frozen_foods"
    HOUSEHOLD_CLEANING = "household_cleaning"
    PERSONAL_CARE_BEAUTY = "personal_care_beauty"
    OTHER = "other"


DEPARTMENT_CATALOG: dict[str, dict[str, str]] = {
    Department.MOBILES_TABLETS.value: {
        "department_id": Department.MOBILES_TABLETS.value,
        "name_en": "Mobiles & Tablets",
        "name_ar": "الموبايلات والتابلت والإكسسوارات",
        "sector": "Tech & Electronics",
        "view_name": "v_dept_mobiles_tablets",
    },
    Department.COMPUTING.value: {
        "department_id": Department.COMPUTING.value,
        "name_en": "Computing & Laptops",
        "name_ar": "اللابتوب والكمبيوتر ومستلزماته",
        "sector": "Tech & Electronics",
        "view_name": "v_dept_computing",
    },
    Department.ELECTRONICS_TV.value: {
        "department_id": Department.ELECTRONICS_TV.value,
        "name_en": "Electronics, TVs & Audio",
        "name_ar": "الإلكترونيات والشاشات والصوتيات",
        "sector": "Tech & Electronics",
        "view_name": "v_dept_electronics_tv",
    },
    Department.HOME_APPLIANCES.value: {
        "department_id": Department.HOME_APPLIANCES.value,
        "name_en": "Home & Kitchen Appliances",
        "name_ar": "الأجهزة المنزلية والكهربائية",
        "sector": "Tech & Electronics",
        "view_name": "v_dept_home_appliances",
    },
    Department.FRESH_MEATS_POULTRY.value: {
        "department_id": Department.FRESH_MEATS_POULTRY.value,
        "name_en": "Fresh Meats, Poultry & Seafood",
        "name_ar": "اللحوم والدواجن والأسماك",
        "sector": "Food & Supermarket",
        "view_name": "v_dept_fresh_meats_poultry",
    },
    Department.DAIRY_CHEESE_EGGS.value: {
        "department_id": Department.DAIRY_CHEESE_EGGS.value,
        "name_en": "Dairy, Cheese & Eggs",
        "name_ar": "الألبان والجبن والبيض",
        "sector": "Food & Supermarket",
        "view_name": "v_dept_dairy_cheese_eggs",
    },
    Department.FRUITS_VEGETABLES.value: {
        "department_id": Department.FRUITS_VEGETABLES.value,
        "name_en": "Fruits & Vegetables",
        "name_ar": "الخضروات والفواكه الطازجة",
        "sector": "Food & Supermarket",
        "view_name": "v_dept_fruits_vegetables",
    },
    Department.GROCERY_PANTRY.value: {
        "department_id": Department.GROCERY_PANTRY.value,
        "name_en": "Grocery & Dry Pantry",
        "name_ar": "البقالة والسلع الغذائية الجافة",
        "sector": "Food & Supermarket",
        "view_name": "v_dept_grocery_pantry",
    },
    Department.BEVERAGES.value: {
        "department_id": Department.BEVERAGES.value,
        "name_en": "Beverages, Tea & Coffee",
        "name_ar": "المشروبات والعصائر والشاي والقهوة",
        "sector": "Food & Supermarket",
        "view_name": "v_dept_beverages",
    },
    Department.BAKERY_SNACKS.value: {
        "department_id": Department.BAKERY_SNACKS.value,
        "name_en": "Bakery, Sweets & Snacks",
        "name_ar": "المخبوزات والحلويات والسناكس",
        "sector": "Food & Supermarket",
        "view_name": "v_dept_bakery_snacks",
    },
    Department.FROZEN_FOODS.value: {
        "department_id": Department.FROZEN_FOODS.value,
        "name_en": "Frozen Foods",
        "name_ar": "الأطعمة المجمدة",
        "sector": "Food & Supermarket",
        "view_name": "v_dept_frozen_foods",
    },
    Department.HOUSEHOLD_CLEANING.value: {
        "department_id": Department.HOUSEHOLD_CLEANING.value,
        "name_en": "Household & Cleaning Supplies",
        "name_ar": "المنظفات والورقيات ومستلزمات المنزل",
        "sector": "Home & Care",
        "view_name": "v_dept_household_cleaning",
    },
    Department.PERSONAL_CARE_BEAUTY.value: {
        "department_id": Department.PERSONAL_CARE_BEAUTY.value,
        "name_en": "Personal Care & Beauty",
        "name_ar": "العناية الشخصية والجمال",
        "sector": "Home & Care",
        "view_name": "v_dept_personal_care_beauty",
    },
    Department.OTHER.value: {
        "department_id": Department.OTHER.value,
        "name_en": "Other Categories",
        "name_ar": "أقسام أخرى",
        "sector": "General",
        "view_name": "v_dept_other",
    },
}


# Keyword rules ordered by specificity: (department, canonical_category, regex_pattern)
_CLASSIFICATION_RULES: list[tuple[str, str, re.Pattern]] = [
    # 1. Computing & Laptops (اللابتوب والكمبيوتر) — before 'apple' fruit or general electronics
    (
        Department.COMPUTING.value,
        "Computing & Laptops",
        re.compile(
            r"\b(laptop|notebook|macbook|imac|mac mini|mac studio|mac pro|vivobook|ideapad|thinkpad|omnibook|zenbook|legion|loq|inspiron|latitude|vostro|pavilion|victus|omen|tuf gaming|rog strix|"
            r"desktop|all-in-one pc|monitor|printer|scanner|router|modem|switch|external hard|ssd|flash drive|usb drive|memory card|sd card|keyboard|mouse|mousepad|webcam|laptop bag|backpack|bag cross|bange|case logic|sleeve|arctic hunter|hub|docking|card reader|ugreen|wi-fi|tp-link|d-link|mercusys|tendacn|viewsonic|j5create|sandisk|kingston|lexar|crucial|"
            r"computing|computers|"
            r"لابتوب|لاب توب|للابتوب|كمبيوتر|شاشة كمبيوتر|فيوسونيك|شاشة لينوفو|معدل تحديث|طابعة|حبر للطابعات|راوتر|سويتش|تي بي-لينك|تي بي لينك|واي فاي|محول usb|هارد|فلاشة|فلاش|كارت ميموري|سانديسك|كينجستون|قارئ البطاقات|كيبورد|لوحة مفاتيح|لوحة المفاتيح|ماوس|ماوس باد|شنطة لاب|شنطة ظهر|حقيبه ظهر|حقيبة ظهر|شنطة كتف|حقيبة كتف|اركتيك هانتر|سمارت جيت)\b",
            re.I,
        ),
    ),
    # 2. Personal Care & Beauty (العناية الشخصية والجمال) — before appliances for shavers/trimmers/hair care/massagers
    (
        Department.PERSONAL_CARE_BEAUTY.value,
        "Personal Care & Beauty",
        re.compile(
            r"\b(shampoo|conditioner|body wash|face wash|cleansing gel|shower gel|soap|deodorant|toothpaste|toothbrush|mouthwash|"
            r"skincare|moisturizer|sunscreen|spf50|niacinamide|hyaluronic|face mask|mud mask|serum|lotion|cosmetic|makeup|perfume|fragrance|diaper|pampers|sanitary napkin|hair removal|shaving|razor|trimmer|shaver|grooming|vgr|epilator|hair dryer|hair straightener|hair curler|stylist|rush brush|walkingpad|nebulizer|blood pressure|thermometer|glucose|pulse oximeter|granzia|clarinose|"
            r"شامبو|بلسم|شاور جل|صابون|مزيل عرق|معجون أسنان|فرشاة أسنان|غسول|كريم|سيروم|لوشن|مكياج|عطر|برفان|حفاضات|بامبرز|"
            r"ماكينة حلاقة|ماكينه حلاقه|ماكينة تشذيب|ماكينة قص|حلاقة اللحية|إزالة الشعر|إزالة شعر|عناية شخصية|مكواة شعر|استشوار|سشوار|مجفف شعر|فرشاة شعر|فرشاة فرد الشعر|راش براش|"
            r"مساج|المساج|تدفئة كهربائية|قياس ضغط الدم|جهاز قياس ضغط|جهاز الاستنشاق|استنشاق البخار|جهاز مشي|جرانزيا|كلارينوز|تنظيف الأنف|وسادة هوائية|مرتبة هوائية)\b",
            re.I,
        ),
    ),
    # 3. Home Appliances (الأجهزة المنزلية والكهربائية) — before food categories (e.g. 'مفرمة لحوم', 'عصارة فواكه', 'مطحنة قهوة')
    (
        Department.HOME_APPLIANCES.value,
        "Home Appliances",
        re.compile(
            r"\b(appliance|refrigerator|fridge|freezer|washing machine|washer|dryer|dishwasher|air conditioner|split ac|"
            r"water heater|water dispenser|cooker|oven|stove|microwave|air fryer|blender|hand blender|chopper|mincer|juicer|coffee grinder|mixer|stand mixer|food processor|kettle|"
            r"coffee maker|espresso machine|toaster|sandwich maker|waffle maker|snack maker|grill|iron|garment steamer|vacuum cleaner|fan|ventilator|air cooler|heater|insect killer|scale|"
            r"hood|built-in hood|hob|gas hob|cooktop|water filter|air purifier|tank filter|cartridge|arzum|okka|sokany|black\+decker|russell hobbs|braun|kenwood|moulinex|delonghi|nespresso|dolce gusto|"
            r"ثلاجة|ديب فريزر|فريزر|غسالة|مجفف|غسالة أطباق|تكييف|مكيف|مبرد هواء|سخان|دفاية|مبرد مياه|مبرد مياة|كولديير|بوتاجاز|بوتجاز|مسطح غاز|مسطح كهربائي|مسطح|بلت إن|فرن|ميكروويف|إير فراير|مقلاة هوائية|قلاية بدون زيت|قلاية|"
            r"خلاط|هاند بلندر|مضرب يدوي|مضرب بيض|كبة|قطاعة|مفرمة|عصارة|مطحنة|عجان|عجانة|ماكينة مطبخ|محضر طعام|حلة طهي|غلاية|غلايه|كاتل|ماكينة قهوة|صانعة القهوة|تحضير القهوة|آلة صنع الإسبريسو|صانع ساندوتش|ساندوتش ميكر|سناك ميكر|جريل|شواية|مكواة|مكواه|كي بالبخار|بخار|تنظيف بالبخار|مكنسة|مروحة|شفاط|شفاط مطبخ|شفاط هرمي|ميزان مطبخ|صاعق ناموس|فلتر مياه|فلتر تانك|فلتر ro|تانك برو|تانك باور|فلاتر|شمعة فلتر|شموع فلتر|اوكا|أوكا|سوكاني|سوكانى|ميلك شيك|سلاش)\b",
            re.I,
        ),
    ),
    # 4. Electronics, TVs & Audio (الإلكترونيات والشاشات والصوتيات)
    (
        Department.ELECTRONICS_TV.value,
        "Electronics, TVs & Audio",
        re.compile(
            r"\b(television|smart tv|led tv|oled|qled|4k uhd|55 inch|65 inch|50 inch|43 inch|32 inch|receiver|projector|nvr|network video recorder|imou|"
            r"soundbar|soundcore boom|bugani|home theater|speaker|headphone|over-ear|on-ear|microphone|maono|boya|playstation|ps5|ps4|xbox|nintendo|fifa|game disc|dualshock|dualsense|gamepad|controller|joystick|vr|virtual reality|camera|gopro|ring light|tripod|power station|smart gate|electronics|"
            r"تلفزيون|تليفزيون|شاشة سمارت|شاشة تلفزيون|حامل حائط للشاشات|حامل حائط.*للشاشات|حامل شاشة|حامل تليفزيون|رسيفر|ريسيفر|ساوند بار|صب ووفر|صب|مكبر صوت|سماعة رأس|سماعة محمولة|جهاز مزج الصوت|ميكروفون|بويا|"
            r"بلايستيشن|بلاي ستيشن|لعبة فيفا|قرص لعبة|إكس بوكس|نينتندو|مشغل ألعاب|يد تحكم|ذراع تحكم|نظارة الواقع الافتراضي|كاميرا|حامل ثلاثي|ترايبود|جيمبال|رينج لايت|بروجيكتور|محطة طاقة محمولة|محطة طاقة|إلكترونيات)\b",
            re.I,
        ),
    ),
    # 5. Mobiles & Tablets (الموبايلات والتابلت والإكسسوارات)
    (
        Department.MOBILES_TABLETS.value,
        "Mobiles & Tablets",
        re.compile(
            r"\b(iphone|ipad|xpad|apple watch|apple pencil|penciltouch|airtag|galaxy|redmi|poco|xiaomi|oppo|realme|infinix|tecno|honor|vivo|huawei|matepad|nokia|hmd|itel|nothing phone|motorola|"
            r"smartphone|mobile phone|cell phone|android phone|ios phone|feature phone|landline phone|phones-tablets|phones & tablets|mobiles|tablet|dual sim|5g|4g lte|microsd|microsdhc|microsdxc|otg|"
            r"smart watch|smartwatch|smart band|smart ring|earbuds|spacebuds|airpods|buds|freebuds|soundcore|power bank|powerbank|magsafe|phone charger|wall charger|car charger|wireless charger|charger|chargers|adapter|"
            r"usb-c|type-c|lightning|cable|cords|screen protector|lens protector|phone case|silicone case|clear case|cover|holder|car mount|earphone|stylus|smart track|selfie stick|ravpower|joyroom|oraimo|relo|choetech|promate|belkin|baseus|cellularline|"
            r"موبايل|هاتف|للهواتف الذكية|تليفون|آيفون|ايفون|آيباد|ايباد|أيباد|اى باد|ميت باد|لينوفو تاب|تابلت|هونر|شاومي|ريدمي|بوكو|سامسونج|جلاكسي|جالاكسي|أوبو|اوبو|ريلمي|انفينكس|إنفينيكس|تكنو|فيفو|هواوي|نوكيا|"
            r"بشرحتين|شريحتين|ساعة ذكية|سمارت ووتش|سوار ذكي|خاتم ذكي|ساعة|ساعه|سماعة بلوتوث|سماعة أذن|سماعات أذن|سماعات|سماعة|سماعه|بادز|إيربودز|ايربودز|ساوندكور|باور بانك|بطارية متنقلة|راف باور|ريلو باور|جوي روم|اورايمو|شاحن موبايل|شاحن حائط|شاحن سيارة|شاحن سريع|شاحن|شواحن|محول منزلي|محول جداري|كابل|كبل|وصلة|تايب سي|لايتنج|جراب|كفر|اسكرينة|لزقة حماية|حماية شاشة|ريتشي|قلم ذكي|قلم لمس|حامل موبايل|حامل سيارة|حامل السيارة)\b",
            re.I,
        ),
    ),
    # 6. Household & Cleaning (المنظفات والورقيات والأدوات المنزلية)
    (
        Department.HOUSEHOLD_CLEANING.value,
        "Household & Cleaning",
        re.compile(
            r"\b(detergent|laundry|ariel|persil|tide|downy|fabric softener|bleach|clorox|dishwash|fairy|pril|"
            r"disinfectant|dettol|toilet paper|tissue|kitchen towel|trash bag|air freshener|insecticide|water bottle|"
            r"منظف|منظفات|مسحوق غسيل|أريال|برسيل|تايد|داوني|معطر|كلور|فيري|بريل|مطهر|ديتول|مناديل|بكر تواليت|زجاجة مياه|زجاجة تريتان|زجاجة مطبوعة|كوينشر زجاجة|زجاجة لحفظ المياه)\b",
            re.I,
        ),
    ),
    # 7. Frozen Foods (المجمدات) — before fresh meats & vegetables so frozen chicken/fries match here
    (
        Department.FROZEN_FOODS.value,
        "Frozen Foods",
        re.compile(
            r"\b(frozen|french fries|ice cream|nuggets|strips|"
            r"مجمد|مجمدة|مجمدات|آيس كريم|ناجتس|ستربس|بطاطس نصف مقلية)\b",
            re.I,
        ),
    ),
    # 8. Bakery & Snacks (المخبوزات والحلويات والسناكس) — before Dairy so 'Dairy Milk Chocolate' matches snacks
    (
        Department.BAKERY_SNACKS.value,
        "Bakery & Snacks",
        re.compile(
            r"\b(bread|toast|croissant|bakery|biscuit|cookie|wafer|chocolate|candy|chips|crisps|popcorn|nuts|almonds|"
            r"خبز|عيش|توست|كرواسون|مخبوزات|بسكويت|كوكيز|ويفر|شوكولاتة|شيبسي|مقرمشات|مكسرات)\b",
            re.I,
        ),
    ),
    # 9. Beverages (المشروبات والعصائر والشاي والقهوة)
    (
        Department.BEVERAGES.value,
        "Beverages, Tea & Coffee",
        re.compile(
            r"\b(tea|coffee|nescafe|espresso|cappuccino|mineral water|sparkling water|juice|nectar|cola|soda|soft drink|energy drink|"
            r"شاي|قهوة|نسكافيه|إسبريسو|مياه معدنية|عصير|مشروب|مشروبات|كولا|صودا)\b",
            re.I,
        ),
    ),
    # 10. Fresh Meats, Poultry & Seafood (اللحوم والدواجن والأسماك)
    (
        Department.FRESH_MEATS_POULTRY.value,
        "Fresh Meats & Poultry",
        re.compile(
            r"\b(meat|beef|veal|lamb|mutton|minced|steak|sausage|kofta|burger|poultry|chicken|duck|turkey|"
            r"seafood|fish|shrimp|salmon|tuna fillet|butcher|"
            r"لحم|لحوم|لحمة|كندوز|بتلو|ضاني|مفروم|كفتة|سجق|برجر|فراخ|دجاج|دواجن|بط|رومي|بانيه|شيش|سمك|أسماك|جمبري|سلمون)\b",
            re.I,
        ),
    ),
    # 11. Dairy, Cheese & Eggs (الألبان والجبن والبيض)
    (
        Department.DAIRY_CHEESE_EGGS.value,
        "Dairy, Cheese & Eggs",
        re.compile(
            r"\b(milk|dairy|cheese|cheddar|mozzarella|feta|roumy|kiri|labneh|yogurt|yoghurt|butter|cream|eggs?|"
            r"لبن|حليب|ألبان|جبن|جبنة|موتزاريلا|شيدر|فيتا|رومي|قشطة|زبدة|زبادي|رايب|بيض)\b",
            re.I,
        ),
    ),
    # 12. Fruits & Vegetables (الخضروات والفواكه)
    (
        Department.FRUITS_VEGETABLES.value,
        "Fruits & Vegetables",
        re.compile(
            r"\b(fresh fruit|fresh vegetable|tomato|potato|onion|garlic|cucumber|carrot|apple fruit|banana|orange|mango|"
            r"خضار|خضروات|فواكه|فاكهة|طماطم|بطاطس|بصل|ثوم|خيار|جزر|تفاح|موز|برتقال|مانجو|ليمون)\b",
            re.I,
        ),
    ),
    # 13. Grocery & Pantry (البقالة والسلع الغذائية الجافة)
    (
        Department.GROCERY_PANTRY.value,
        "Grocery & Pantry",
        re.compile(
            r"\b(grocery|groceries|supermarket|food cupboard|rice|pasta|macaroni|spaghetti|noodles|flour|sugar|salt|"
            r"cooking oil|sunflower oil|corn oil|olive oil|ghee|honey|jam|peanut butter|tahini|halawa|vinegar|sauce|ketchup|mayonnaise|tuna|beans|foul|lentils|chickpeas|spices|"
            r"بقالة|سوبرماركت|أرز|مكرونة|شعرية|لسان عصفور|دقيق|سكر|ملح|زيت|سمن|سمنة|عسل|مربى|طحينة|حلاوة|خل|صلصة|كاتشب|مايونيز|تونة|فول|عدس|توابل|بهارات)\b",
            re.I,
        ),
    ),
]


# Direct mapping for source category keys/names
_DIRECT_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "ios-phones": (Department.MOBILES_TABLETS.value, "iOS Phones"),
    "android-phones": (Department.MOBILES_TABLETS.value, "Android Phones"),
    "cell-phones": (Department.MOBILES_TABLETS.value, "Cell Phones"),
    "mobile-phones": (Department.MOBILES_TABLETS.value, "Mobile Phones"),
    "phones-tablets": (Department.MOBILES_TABLETS.value, "Mobiles & Tablets"),
    "phones & tablets": (Department.MOBILES_TABLETS.value, "Mobiles & Tablets"),
    "phones tablets": (Department.MOBILES_TABLETS.value, "Mobiles & Tablets"),
    "smartphones": (Department.MOBILES_TABLETS.value, "Smartphones"),
    "mobiles": (Department.MOBILES_TABLETS.value, "Mobile Phones"),
    "iphone": (Department.MOBILES_TABLETS.value, "iPhone"),
    "ipad": (Department.MOBILES_TABLETS.value, "iPad"),
    "apple watch": (Department.MOBILES_TABLETS.value, "Apple Watch"),
    "airpods": (Department.MOBILES_TABLETS.value, "AirPods"),
    "iphone lens": (Department.MOBILES_TABLETS.value, "Mobile Accessories"),
    "charging essentials": (Department.MOBILES_TABLETS.value, "Chargers & Adapters"),
    "cables & cords": (Department.MOBILES_TABLETS.value, "Cables & Cords"),
    "tablets": (Department.MOBILES_TABLETS.value, "Tablets"),
    "smartwatches": (Department.MOBILES_TABLETS.value, "Smartwatches & Wearables"),
    "chargers": (Department.MOBILES_TABLETS.value, "Chargers & Adapters"),
    "accessories": (Department.MOBILES_TABLETS.value, "Mobile Accessories"),
    "mobile accessories": (Department.MOBILES_TABLETS.value, "Mobile Accessories"),
    "wearables": (Department.MOBILES_TABLETS.value, "Smartwatches & Wearables"),
    "landline-phones": (Department.MOBILES_TABLETS.value, "Landline Phones"),
    "laptops": (Department.COMPUTING.value, "Laptops"),
    "laptops & pcs": (Department.COMPUTING.value, "Laptops & PCs"),
    "computing & laptops": (Department.COMPUTING.value, "Computing & Laptops"),
    "imac": (Department.COMPUTING.value, "iMac & Desktops"),
    "mac": (Department.COMPUTING.value, "Mac & Laptops"),
    "computing": (Department.COMPUTING.value, "Computing & Laptops"),
    "computers": (Department.COMPUTING.value, "Computing & Laptops"),
    "storage": (Department.COMPUTING.value, "Data Storage"),
    "networking": (Department.COMPUTING.value, "Networking & Routers"),
    "electronics": (Department.ELECTRONICS_TV.value, "Electronics & TVs"),
    "televisions": (Department.ELECTRONICS_TV.value, "Televisions"),
    "tvs": (Department.ELECTRONICS_TV.value, "Televisions"),
    "speaker": (Department.ELECTRONICS_TV.value, "Speakers & Audio"),
    "audio": (Department.ELECTRONICS_TV.value, "Speakers & Audio"),
    "tv & audio": (Department.ELECTRONICS_TV.value, "Televisions & Audio"),
    "electronics & tvs": (Department.ELECTRONICS_TV.value, "Electronics & TVs"),
    "electronics & appliances": (Department.ELECTRONICS_TV.value, "Electronics & Appliances"),
    "appliances": (Department.HOME_APPLIANCES.value, "Home Appliances"),
    "home appliances": (Department.HOME_APPLIANCES.value, "Home Appliances"),
    "home-appliances": (Department.HOME_APPLIANCES.value, "Home Appliances"),
    "small domestic appliances": (Department.HOME_APPLIANCES.value, "Home Appliances"),
    "large home appliances": (Department.HOME_APPLIANCES.value, "Home Appliances"),
    "fresh_meats_poultry": (Department.FRESH_MEATS_POULTRY.value, "Fresh Meats & Poultry"),
    "meats": (Department.FRESH_MEATS_POULTRY.value, "Fresh Meats & Poultry"),
    "dairy_cheese_eggs": (Department.DAIRY_CHEESE_EGGS.value, "Dairy, Cheese & Eggs"),
    "fruits_vegetables": (Department.FRUITS_VEGETABLES.value, "Fruits & Vegetables"),
    "grocery_pantry": (Department.GROCERY_PANTRY.value, "Grocery & Pantry"),
    "supermarket": (Department.GROCERY_PANTRY.value, "Grocery & Pantry"),
    "groceries": (Department.GROCERY_PANTRY.value, "Grocery & Pantry"),
    "beverages": (Department.BEVERAGES.value, "Beverages, Tea & Coffee"),
    "bakery_snacks": (Department.BAKERY_SNACKS.value, "Bakery & Snacks"),
    "frozen_foods": (Department.FROZEN_FOODS.value, "Frozen Foods"),
    "household_cleaning": (Department.HOUSEHOLD_CLEANING.value, "Household & Cleaning"),
    "personal_care_beauty": (Department.PERSONAL_CARE_BEAUTY.value, "Personal Care & Beauty"),
    "personal care": (Department.PERSONAL_CARE_BEAUTY.value, "Personal Care & Beauty"),
    "health-beauty": (Department.PERSONAL_CARE_BEAUTY.value, "Personal Care & Beauty"),
    "health & beauty": (Department.PERSONAL_CARE_BEAUTY.value, "Personal Care & Beauty"),
    "beauty": (Department.PERSONAL_CARE_BEAUTY.value, "Personal Care & Beauty"),
    "headphones": (Department.ELECTRONICS_TV.value, "Headphones & Audio"),
    "headphone": (Department.ELECTRONICS_TV.value, "Headphones & Audio"),
    "headphones & earphones": (Department.ELECTRONICS_TV.value, "Headphones & Audio"),
    "cameras": (Department.ELECTRONICS_TV.value, "Cameras & Photography"),
    "camera": (Department.ELECTRONICS_TV.value, "Cameras & Photography"),
    "mac accessories": (Department.COMPUTING.value, "Mac & PC Accessories"),
    "display": (Department.COMPUTING.value, "Computer Displays"),
    "displays": (Department.COMPUTING.value, "Computer Displays"),
    "screen extender": (Department.COMPUTING.value, "Display Extenders"),
    "software": (Department.COMPUTING.value, "Software & Services"),
    "diffuser": (Department.HOUSEHOLD_CLEANING.value, "Home Fragrance & Diffusers"),
    "applecare": (Department.OTHER.value, "Warranty & AppleCare"),
    "iphone case": (Department.MOBILES_TABLETS.value, "iPhone Cases"),
    "ipad case": (Department.MOBILES_TABLETS.value, "iPad Cases"),
    "mice & trackpad": (Department.COMPUTING.value, "Mice & Trackpads"),
}


# Aliases so CLI users can pass friendly names like --department electronics, --department meats, --department phones
DEPARTMENT_ALIASES: dict[str, str] = {
    "phones": Department.MOBILES_TABLETS.value,
    "mobiles": Department.MOBILES_TABLETS.value,
    "mobile": Department.MOBILES_TABLETS.value,
    "mobiles_tablets": Department.MOBILES_TABLETS.value,
    "tablets": Department.MOBILES_TABLETS.value,
    "computing": Department.COMPUTING.value,
    "laptops": Department.COMPUTING.value,
    "computers": Department.COMPUTING.value,
    "electronics": Department.ELECTRONICS_TV.value,
    "electronics_tv": Department.ELECTRONICS_TV.value,
    "tv": Department.ELECTRONICS_TV.value,
    "tvs": Department.ELECTRONICS_TV.value,
    "appliances": Department.HOME_APPLIANCES.value,
    "home_appliances": Department.HOME_APPLIANCES.value,
    "meats": Department.FRESH_MEATS_POULTRY.value,
    "meat": Department.FRESH_MEATS_POULTRY.value,
    "poultry": Department.FRESH_MEATS_POULTRY.value,
    "fresh_meats_poultry": Department.FRESH_MEATS_POULTRY.value,
    "dairy": Department.DAIRY_CHEESE_EGGS.value,
    "dairy_cheese_eggs": Department.DAIRY_CHEESE_EGGS.value,
    "fruits_vegetables": Department.FRUITS_VEGETABLES.value,
    "produce": Department.FRUITS_VEGETABLES.value,
    "grocery": Department.GROCERY_PANTRY.value,
    "groceries": Department.GROCERY_PANTRY.value,
    "supermarket": Department.GROCERY_PANTRY.value,
    "grocery_pantry": Department.GROCERY_PANTRY.value,
    "beverages": Department.BEVERAGES.value,
    "drinks": Department.BEVERAGES.value,
    "bakery": Department.BAKERY_SNACKS.value,
    "snacks": Department.BAKERY_SNACKS.value,
    "bakery_snacks": Department.BAKERY_SNACKS.value,
    "frozen": Department.FROZEN_FOODS.value,
    "frozen_foods": Department.FROZEN_FOODS.value,
    "cleaning": Department.HOUSEHOLD_CLEANING.value,
    "household": Department.HOUSEHOLD_CLEANING.value,
    "household_cleaning": Department.HOUSEHOLD_CLEANING.value,
    "beauty": Department.PERSONAL_CARE_BEAUTY.value,
    "personal_care": Department.PERSONAL_CARE_BEAUTY.value,
    "personal_care_beauty": Department.PERSONAL_CARE_BEAUTY.value,
}


def resolve_department_alias(name: Optional[str]) -> Optional[str]:
    """Resolve a user-supplied department name or alias to its canonical Department code."""
    if not name:
        return None
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    if key in DEPARTMENT_CATALOG:
        return key
    if key in DEPARTMENT_ALIASES:
        return DEPARTMENT_ALIASES[key]
    raise ValueError(
        f"Unknown department '{name}'. Valid departments: "
        f"{', '.join(DEPARTMENT_CATALOG.keys())} "
        f"(or aliases: phones, laptops, electronics, appliances, meats, dairy, grocery, beverages, cleaning, beauty)"
    )


# Granular subcategory rules: (department, canonical_category, subcategory, regex_pattern)
_SUBCATEGORY_RULES: list[tuple[str, str, str, re.Pattern]] = [
    # ─── Mobiles & Tablets ──────────────────────────────────────────
    ("mobiles_tablets", "Smartphones", "iOS Phones",
     re.compile(r"\b(iphone|i\s+phone|آيفون|ايفون|apple\s+1[1-8]\b|apple\s+xs|apple\s+xr|apple\s+se)\b", re.I)),
    ("mobiles_tablets", "Smartphones", "Android Phones",
     re.compile(r"\b(galaxy|samsung\s+[asfmz]\d+|samsung\s+galaxy|samsung\s+note|samsung\s+ultra|galaxy-?[asfmz]\d+|redmi|poco|xiaomi|oppo|realme|infinix|انفينكس|إنفينيكس|انفنيكس|tecno|تكنو|vivo|فيفو|honor|هونر|huawei\s+(nova|p\d+|mate|y\d+)|itel|nothing\s+phone|motorola|smart\s+20|سامسونج|شاومي|أوبو|اوبو|ريلمي|هاتف\s+ذكي|smartphone)\b", re.I)),
    ("mobiles_tablets", "Feature Phones", "Feature Phones",
     re.compile(r"\b(nokia|نوكيا|بزراير|girasole|pluzz|hope\s+k\d+|i\s+pro\s+a\d+|feature\s+phone|هاتف\s+محمول\s+عادي|تليفون\s+أرضي|landline|dual\s+sim\s+mobile\s+phone|quad\s+sim)\b", re.I)),
    ("mobiles_tablets", "Tablets", "iPads",
     re.compile(r"\b(ipad|آيباد|ايباد|أيباد|اى باد)\b", re.I)),
    ("mobiles_tablets", "Tablets", "Android Tablets",
     re.compile(r"\b(tablet|matepad|ميت باد|لينوفو\s+تاب|تابلت|galaxy\s+tab|xpad|لوحي)\b", re.I)),
    ("mobiles_tablets", "Smartwatches & Wearables", "Apple Watch",
     re.compile(r"\b(apple\s+watch|ساعة\s+آبل|ساعة\s+ابل)\b", re.I)),
    ("mobiles_tablets", "Smartwatches & Wearables", "Smartwatches",
     re.compile(r"\b(smart\s*watch|ساعة\s+ذكية|سمارت\s+ووتش|kieslect|amazfit|ساعة\s+(يد\s+)?(شاومي|هواوي|سامسونج))\b", re.I)),
    ("mobiles_tablets", "Smartwatches & Wearables", "Smart Bands & Fitness Trackers",
     re.compile(r"\b(smart\s*band|fitness\s+tracker|سوار\s+ذكي|فيت\s*بت|fitbit|باند\s+\d+)\b", re.I)),
    ("mobiles_tablets", "Smartwatches & Wearables", "Smart Rings",
     re.compile(r"\b(smart\s*ring|خاتم\s+ذكي)\b", re.I)),
    ("mobiles_tablets", "Mobile Audio", "AirPods",
     re.compile(r"\b(airpods|ايربودز|إيربودز|airpod)\b", re.I)),
    ("mobiles_tablets", "Mobile Audio", "Wireless Earbuds",
     re.compile(r"\b(earbuds|spacebuds|freebuds|soundcore|buds|بادز|سماعة\s+بلوتوث|سماعات\s+أذن|سماعات\s+اذن|سماعة\s+أذن|سماعة\s+اذن|سماعات\s+لاسلكية|سماعة\s+لاسلكية|tws|wireless\s+earphones?)\b", re.I)),
    ("mobiles_tablets", "Mobile Audio", "Wired Earphones",
     re.compile(r"\b(سماعة\s+سلك|سماعات\s+سلك|wired\s+earphone|earphone\s+with\s+mic|earphones?\b|سماعة\s+أذن\s+سلكية)\b", re.I)),
    ("mobiles_tablets", "Power & Charging", "Power Banks",
     re.compile(r"\b(power\s*bank|باور\s*بانك|بطارية\s+متنقلة|شاحن\s+متنقل|ravpower|راف\s*باور|ريلو\s*باور)\b", re.I)),
    ("mobiles_tablets", "Power & Charging", "Wireless & MagSafe Chargers",
     re.compile(r"\b(wireless\s+charger|magsafe|شاحن\s+لاسلكي|شاحن\s+ماج\s*سيف|شاحن\s+مغناطيسي)\b", re.I)),
    ("mobiles_tablets", "Power & Charging", "Car Chargers",
     re.compile(r"\b(car\s+charger|شاحن\s+سيارة|شاحن\s+عربية)\b", re.I)),
    ("mobiles_tablets", "Power & Charging", "Wall Chargers & Adapters",
     re.compile(r"\b(wall\s+charger|phone\s+charger|charger|adapter|charging\s+essentials|شاحن\s+حائط|شاحن\s+سريع|شاحن\s+موبايل|شواحن|محول\s+جداري|محول\s+منزلي|رأس\s+شاحن|شاحن\b)\b", re.I)),
    ("mobiles_tablets", "Cables & Connectivity", "USB-C Cables",
     re.compile(r"\b(usb-c|type-c|تايب\s*سي|كابل\s+تايب|وصلة\s+تايب)\b", re.I)),
    ("mobiles_tablets", "Cables & Connectivity", "Lightning Cables",
     re.compile(r"\b(lightning|لايتنج|لايتننج|كابل\s+ايفون|كابل\s+آيفون)\b", re.I)),
    ("mobiles_tablets", "Cables & Connectivity", "Cables & Cords",
     re.compile(r"\b(cable|cords|كابل|كبل|وصلة\s+شحن|سلك\s+شحن)\b", re.I)),
    ("mobiles_tablets", "Mobile Protection & Accessories", "Screen & Lens Protectors",
     re.compile(r"\b(screen\s+protector|lens\s+protector|اسكرينة|لزقة\s+حماية|حماية\s+شاشة|واقي\s+شاشة|زجاج\s+حماية|iphone\s+lens)\b", re.I)),
    ("mobiles_tablets", "Mobile Protection & Accessories", "Cases & Covers",
     re.compile(r"\b(case|cover|جراب|كفر|غطاء\s+حماية|iphone\s+case|ipad\s+case|silicone\s+case|clear\s+case|leather\s+case)\b", re.I)),
    ("mobiles_tablets", "Mobile Protection & Accessories", "Phone Holders & Mounts",
     re.compile(r"\b(phone\s+holder|car\s+mount|osmo\s+mobile|gimbal|حامل\s+موبايل|حامل\s+سيارة|حامل\s+السيارة|ستاند\s+موبايل)\b", re.I)),
    ("mobiles_tablets", "Mobile Protection & Accessories", "Stylus & Pens",
     re.compile(r"\b(stylus|apple\s+pencil|penciltouch|قلم\s+ذكي|قلم\s+لمس)\b", re.I)),
    ("mobiles_tablets", "Smartphones", "Smartphones",
     re.compile(r"\b(dual\s+sim|4g\s+lte|5g\b|موبايل|هاتف)\b", re.I)),

    # ─── Computing & Laptops ─────────────────────────────────────────
    ("computing", "Laptops", "MacBooks",
     re.compile(r"\b(macbook|ماك\s*بوك)\b", re.I)),
    ("computing", "Laptops", "Gaming Laptops",
     re.compile(r"\b(legion|loq|rog\s+strix|tuf\s+gaming|victus|omen|gaming\s+laptop|لابتوب\s+ألعاب|لابتوب\s+جيمنج)\b", re.I)),
    ("computing", "Laptops", "Laptops & Notebooks",
     re.compile(r"\b(laptop|notebook|vivobook|ideapad|thinkpad|zenbook|omnibook|inspiron|latitude|vostro|pavilion|chromebook|لابتوب|لاب\s*توب)\b", re.I)),
    ("computing", "Desktops & All-in-One", "iMac & Mac Desktops",
     re.compile(r"\b(imac|mac\s+mini|mac\s+studio|mac\s+pro)\b", re.I)),
    ("computing", "Desktops & All-in-One", "Desktop PCs & All-in-One",
     re.compile(r"\b(desktop|all-in-one|كمبيوتر\s+مكتبي|كمبيوتر|كيسة\s+كمبيوتر|بي\s*سي)\b", re.I)),
    ("computing", "Software & Services", "Software & Operating Systems",
     re.compile(r"\b(office\s+365|microsoft\s+365|windows\s+11|antivirus|software)\b", re.I)),
    ("computing", "Monitors & Displays", "Computer Monitors",
     re.compile(r"\b(monitor|screen\s+extender|studio\s+display|display\b|شاشة\s+كمبيوتر|شاشة\s+لينوفو|فيوسونيك|viewsonic|معدل\s+تحديث)\b", re.I)),
    ("computing", "Data Storage", "Internal SSDs & Hard Drives",
     re.compile(r"\b(internal\s+ssd|nvme|m\.2|ssd\s+drive|قرص\s+صلب\s+داخلي)\b", re.I)),
    ("computing", "Data Storage", "External Hard Drives & SSDs",
     re.compile(r"\b(external\s+hard|external\s+ssd|my\s+passport|western\s+digital|هارد\s+خارجي|هارد\s+محمول)\b", re.I)),
    ("computing", "Data Storage", "USB Flash Drives",
     re.compile(r"\b(flash\s+drive|usb\s+drive|datatraveler|فلاشة|فلاش\s+ميموري|يو\s+اس\s+بي\s+درايف)\b", re.I)),
    ("computing", "Data Storage", "Memory Cards",
     re.compile(r"\b(memory\s+card|sd\s+card|microsd|كارت\s+ميموري|بطاقة\s+ذاكرة)\b", re.I)),
    ("computing", "Keyboards & Mice", "Mice",
     re.compile(r"\b(mouse|trackpad|ماوس|ماووس)\b", re.I)),
    ("computing", "Keyboards & Mice", "Keyboards",
     re.compile(r"\b(keyboard|كيبورد|لوحة\s+مفاتيح|لوحة\s+المفاتيح)\b", re.I)),
    ("computing", "Keyboards & Mice", "Mouse Pads",
     re.compile(r"\b(mousepad|mouse\s+pad|ماوس\s*باد)\b", re.I)),
    ("computing", "Networking & Routers", "Wi-Fi Routers & Modems",
     re.compile(r"\b(router|modem|راوتر|مودم)\b", re.I)),
    ("computing", "Networking & Routers", "Access Points & Extenders",
     re.compile(r"\b(access\s+point|اكسس\s+بوينت|range\s+extender|مقوي\s+شبكة|wi-fi|واي\s*فاي)\b", re.I)),
    ("computing", "Networking & Routers", "Switches & Network Adapters",
     re.compile(r"\b(switch|سويتش|ethernet|مقسم\s+شبكة|محول\s+شبكة|tp-link|d-link|mercusys|tendacn|تي\s+بي\s*لينك)\b", re.I)),
    ("computing", "Printers & Scanners", "Printers",
     re.compile(r"\b(printer|طابعة)\b", re.I)),
    ("computing", "Printers & Scanners", "Printer Ink & Toner",
     re.compile(r"\b(toner|ink\s+cartridge|refill\s+ink|ink\s+bottle|ink\s+tank|حبر\s+للطابعات|حبر\s+طابعة)\b", re.I)),
    ("computing", "Computer Accessories", "USB Hubs & Docks",
     re.compile(r"\b(hub|docking|موزع\s+يو\s+اس\s+بي|محول\s+usb|card\s+reader|قارئ\s+البطاقات)\b", re.I)),
    ("computing", "Computer Accessories", "Laptop Bags & Sleeves",
     re.compile(r"\b(laptop\s+bag|backpack|sleeve|briefcase|messenger\s+bag|brief\b|شنطة\s+لاب|شنطة\s+ظهر|حقيبة\s+ظهر|حقيبة\s+لابتوب|حقيبه\s+ظهر|شنطة\s+كتف|اركتيك\s+هانتر|bange|case\s+logic|incase|uniq\s+stockholm)\b", re.I)),
    ("computing", "Computer Accessories", "Webcams & Headsets",
     re.compile(r"\b(webcam|كاميرا\s+ويب)\b", re.I)),

    # ─── Electronics, TVs & Audio ───────────────────────────────────
    ("electronics_tv", "Televisions", "Smart TVs",
     re.compile(r"\b(television|smart\s+tv|led\s+tv|standard\s+tv|oled|qled|4k\s+uhd|تلفزيون|تليفزيون|شاشة\s+سمارت|شاشة\s+تلفزيون|\d+\s*بوصة|\d+\s*inch)\b", re.I)),
    ("electronics_tv", "Televisions", "TV Wall Mounts & Brackets",
     re.compile(r"\b(حامل\s+حائط\s*(ل)?للشاشات|حامل\s+شاشة|حامل\s+تليفزيون|wall\s+mount|tv\s+bracket)\b", re.I)),
    ("electronics_tv", "Televisions", "TV Receivers & Streaming",
     re.compile(r"\b(receiver|رسيفر|ريسيفر|tv\s+box|apple\s+tv)\b", re.I)),
    ("electronics_tv", "Audio & Sound Systems", "Soundbars",
     re.compile(r"\b(soundbar|ساوند\s*بار|ساوندبار)\b", re.I)),
    ("electronics_tv", "Audio & Sound Systems", "Portable Bluetooth Speakers",
     re.compile(r"\b(speaker|soundcore\s+boom|bugani|beats\s+pill|مكبر\s+صوت|صب\s+ووفر|سماعة\s+محمولة|صب\b|راديو|radio)\b", re.I)),
    ("electronics_tv", "Audio & Sound Systems", "Over-Ear Headphones",
     re.compile(r"\b(over-ear|on-ear|headphone|headband|headphones\s+&\s+earphones|سماعة\s+رأس|سماعات\s+رأس|sony\s+wh|wh-ch|ult\s+wear|beoplay)\b", re.I)),
    ("electronics_tv", "Audio & Sound Systems", "Microphones & Audio Gear",
     re.compile(r"\b(microphone|ميكروفون|مايك\b|boya|maono|hollyland|dji\s+مايك|جهاز\s+مزج\s+الصوت)\b", re.I)),
    ("electronics_tv", "Gaming Consoles & Accessories", "PlayStation Consoles",
     re.compile(r"\b(playstation|ps5|ps4|بلايستيشن|بلاي\s+ستيشن)\b", re.I)),
    ("electronics_tv", "Gaming Consoles & Accessories", "Xbox Consoles",
     re.compile(r"\b(xbox|إكس\s+بوكس)\b", re.I)),
    ("electronics_tv", "Gaming Consoles & Accessories", "Controllers & Gamepads",
     re.compile(r"\b(controller|gamepad|joystick|dualshock|dualsense|يد\s+تحكم|ذراع\s+تحكم|ريدواجون|كوغار)\b", re.I)),
    ("electronics_tv", "Gaming Consoles & Accessories", "Video Games",
     re.compile(r"\b(fifa|game\s+disc|قرص\s+لعبة|لعبة\s+فيفا)\b", re.I)),
    ("electronics_tv", "Cameras & Photography", "Security & Smart Cameras",
     re.compile(r"\b(security\s+cam|outdoor\s+cam|indoor\s+cam|solocam|nvr|imou|eufy|cameras?|كاميرا\s+مراقبة|كاميرات\s+مراقبة)\b", re.I)),
    ("electronics_tv", "Cameras & Photography", "Action & Digital Cameras",
     re.compile(r"\b(camera|كاميرا|gopro|insta360|إنستا\s*360)\b", re.I)),
    ("electronics_tv", "Cameras & Photography", "Tripods & Ring Lights",
     re.compile(r"\b(tripod|ring\s+light|رينج\s+لايت|ترايبود|حامل\s+ثلاثي|جيمبال|gimbal)\b", re.I)),
    ("electronics_tv", "Projectors & Smart Home", "Home Projectors",
     re.compile(r"\b(projector|بروجكتور|بروجيكتور)\b", re.I)),
    ("electronics_tv", "Projectors & Smart Home", "Power Stations",
     re.compile(r"\b(power\s+station|محطة\s+طاقة|alkaline\s+batteries|بطارية\s+aa)\b", re.I)),

    # ─── Home Appliances ────────────────────────────────────────────
    ("home_appliances", "Large Appliances", "Refrigerators & Freezers",
     re.compile(r"\b(refrigerator|fridge|freezer|ثلاجة|ديب\s+فريزر|فريزر)\b", re.I)),
    ("home_appliances", "Large Appliances", "Washing Machines & Dryers",
     re.compile(r"\b(washing\s+machine|washer|dryer|غسالة|غساله|مجفف)\b", re.I)),
    ("home_appliances", "Large Appliances", "Dishwashers",
     re.compile(r"\b(dishwasher|غسالة\s+أطباق|غساله\s+اطباق|غسالة\s+صحون)\b", re.I)),
    ("home_appliances", "Large Appliances", "Cookers & Ovens",
     re.compile(r"\b(cooker|oven|stove|hob|cooktop|بوتاجاز|بوتجاز|مسطح|فرن|بلت\s+إن)\b", re.I)),
    ("home_appliances", "Large Appliances", "Air Conditioners & Coolers",
     re.compile(r"\b(air\s+conditioner|split\s+ac|تكييف|مكيف|مبرد\s+هواء)\b", re.I)),
    ("home_appliances", "Large Appliances", "Water Heaters",
     re.compile(r"\b(water\s+heater|سخان)\b", re.I)),
    ("home_appliances", "Large Appliances", "Water Dispensers",
     re.compile(r"\b(water\s+dispenser|مبرد\s+مياه|مبرد\s+مياة|كولديير)\b", re.I)),
    ("home_appliances", "Small Kitchen Appliances", "Air Fryers",
     re.compile(r"\b(air\s+fryer|إير\s+فراير|اير\s+فراير|مقلاة\s+هوائية|قلاية\s+بدون\s+زيت|قلاية\b)\b", re.I)),
    ("home_appliances", "Small Kitchen Appliances", "Microwaves",
     re.compile(r"\b(microwave|ميكروويف)\b", re.I)),
    ("home_appliances", "Small Kitchen Appliances", "Blenders & Food Processors",
     re.compile(r"\b(blender|hand\s+blender|chopper|mincer|mixer|stand\s+mixer|food\s+processor|خلاط|هاند\s+بلندر|كبة|قطاعة|مفرمة|عجان|عجانة|محضر\s+طعام|مضرب\s+بيض)\b", re.I)),
    ("home_appliances", "Small Kitchen Appliances", "Coffee Machines & Grinders",
     re.compile(r"\b(coffee\s+maker|espresso|coffee\s+grinder|ماكينة\s+قهوة|صانعة\s+القهوة|مطحنة\s+قهوة|إسبريسو|نسبريسو|اوكا|أوكا|nespresso|delonghi|arzum)\b", re.I)),
    ("home_appliances", "Small Kitchen Appliances", "Electric Kettles",
     re.compile(r"\b(kettle|غلاية|غلايه|كاتل)\b", re.I)),
    ("home_appliances", "Small Kitchen Appliances", "Toasters & Sandwich Makers",
     re.compile(r"\b(toaster|sandwich\s+maker|waffle\s+maker|صانع\s+ساندوتش|ساندوتش\s+ميكر|توستر|سناك\s+ميكر|جريل|شواية)\b", re.I)),
    ("home_appliances", "Small Kitchen Appliances", "Juicers",
     re.compile(r"\b(juicer|عصارة)\b", re.I)),
    ("home_appliances", "Home Care Appliances", "Vacuum Cleaners",
     re.compile(r"\b(vacuum\s+cleaner|vacuum|مكنسة)\b", re.I)),
    ("home_appliances", "Home Care Appliances", "Garment Steamers & Irons",
     re.compile(r"\b(iron|garment\s+steamer|lint\s+remover|مكواة|مكواه|كي\s+بالبخار)\b", re.I)),
    ("home_appliances", "Home Care Appliances", "Fans & Ventilators",
     re.compile(r"\b(fan|ventilator|مروحة|شفاط)\b", re.I)),
    ("home_appliances", "Home Care Appliances", "Heaters",
     re.compile(r"\b(heater|دفاية)\b", re.I)),
    ("home_appliances", "Water Treatment", "Water Filters & Cartridges",
     re.compile(r"\b(water\s+filter|tank\s+filter|فلتر\s+مياه|فلتر\s+تانك|شمعة\s+فلتر|شموع\s+فلتر|تانك\s+برو|تانك\s+باور)\b", re.I)),

    # ─── Personal Care & Beauty ─────────────────────────────────────
    ("personal_care_beauty", "Hair Styling & Grooming", "Hair Trimmers & Shavers",
     re.compile(r"\b(shaver|trimmer|razor|grooming|vgr|epilator|ماكينة\s+حلاقة|ماكينه\s+حلاقه|ماكينة\s+تشذيب|حلاقة)\b", re.I)),
    ("personal_care_beauty", "Hair Styling & Grooming", "Hair Dryers & Straighteners",
     re.compile(r"\b(hair\s+dryer|hair\s+straightener|hair\s+curler|rush\s+brush|مجفف\s+شعر|مكواة\s+شعر|استشوار|سشوار|راش\s+براش)\b", re.I)),
    ("personal_care_beauty", "Personal Health & Wellness", "Health Monitors & Medical",
     re.compile(r"\b(blood\s+pressure|thermometer|glucose|pulse\s+oximeter|nebulizer|قياس\s+ضغط\s+الدم|جهاز\s+قياس\s+ضغط|جهاز\s+الاستنشاق|جرانزيا|كلارينوز)\b", re.I)),
    ("personal_care_beauty", "Personal Health & Wellness", "Massagers & Fitness",
     re.compile(r"\b(massager|walkingpad|مساج|المساج|جهاز\s+مشي|تدفئة\s+كهربائية)\b", re.I)),
    ("personal_care_beauty", "Skincare & Bath", "Facial Cleansers & Serums",
     re.compile(r"\b(face\s+wash|cleansing|serum|niacinamide|hyaluronic|face\s+mask|micellar|غسول|سيروم)\b", re.I)),
    ("personal_care_beauty", "Skincare & Bath", "Moisturizers & Sunscreen",
     re.compile(r"\b(moisturizer|sunscreen|spf|lotion|كريم|مرطب|لوشن|واقي\s+شمس)\b", re.I)),
    ("personal_care_beauty", "Skincare & Bath", "Body Wash & Soap",
     re.compile(r"\b(body\s+wash|shower\s+gel|soap|deodorant|صابون|شاور\s+جل|مزيل\s+عرق)\b", re.I)),
    ("personal_care_beauty", "Hair Care", "Shampoo & Conditioner",
     re.compile(r"\b(shampoo|conditioner|شامبو|بلسم)\b", re.I)),
    ("personal_care_beauty", "Oral Care", "Toothpaste & Toothbrushes",
     re.compile(r"\b(toothpaste|toothbrush|mouthwash|معجون\s+أسنان|فرشاة\s+أسنان)\b", re.I)),
    ("personal_care_beauty", "Fragrances & Cosmetics", "Perfumes & Fragrances",
     re.compile(r"\b(perfume|fragrance|عطر|برفان)\b", re.I)),
    ("personal_care_beauty", "Fragrances & Cosmetics", "Cosmetics & Makeup",
     re.compile(r"\b(makeup|cosmetic|eyeliner|mascara|lipliner|lipstick|highlighter|eyelash|nail|مكياج|كحل|ماسكارا)\b", re.I)),
    ("personal_care_beauty", "Baby Care", "Diapers & Baby Care",
     re.compile(r"\b(diaper|pampers|sanitary\s+napkin|حفاضات|بامبرز)\b", re.I)),

    # ─── Household & Cleaning ───────────────────────────────────────
    ("household_cleaning", "Laundry & Cleaning", "Laundry Detergents",
     re.compile(r"\b(detergent|laundry|ariel|persil|tide|مسحوق\s+غسيل|أريال|برسيل|تايد)\b", re.I)),
    ("household_cleaning", "Laundry & Cleaning", "Dishwashing & Cleaners",
     re.compile(r"\b(dish\s*wash|fairy|pril|clorox|bleach|disinfectant|dettol|stains\s+remover|softener|فيري|بريل|كلور|مطهر|ديتول|منعم\s+أقمشة)\b", re.I)),
    ("household_cleaning", "Household Paper", "Tissues & Paper Towels",
     re.compile(r"\b(toilet\s+paper|tissue|kitchen\s+towel|مناديل|بكر\s+تواليت|ورق\s+مطبخ)\b", re.I)),
    ("household_cleaning", "Bottles & Kitchenware", "Water Bottles & Tumblers",
     re.compile(r"\b(water\s+bottle|quencher|زجاجة\s+مياه|زجاجة\s+تانك|مج\s+حراري|تانك\s+موف)\b", re.I)),
    ("household_cleaning", "Air Care", "Air Fresheners & Diffusers",
     re.compile(r"\b(diffuser|air\s+freshener|معطر|فواحة)\b", re.I)),

    # ─── Supermarket & Food Departments ─────────────────────────────
    ("grocery_pantry", "Pantry Staples", "Rice, Pasta & Grains",
     re.compile(r"\b(rice|pasta|macaroni|spaghetti|noodles|أرز|مكرونة|شعرية|لسان\s+عصفور)\b", re.I)),
    ("grocery_pantry", "Pantry Staples", "Cooking Oils & Ghee",
     re.compile(r"\b(cooking\s+oil|sunflower\s+oil|corn\s+oil|olive\s+oil|ghee|زيت|سمن|سمنة)\b", re.I)),
    ("grocery_pantry", "Pantry Staples", "Sugar, Salt & Spices",
     re.compile(r"\b(sugar|salt|spices|flour|vinegar|سكر|ملح|توابل|بهارات|دقيق|خل)\b", re.I)),
    ("grocery_pantry", "Canned & Packaged Foods", "Canned Goods & Tuna",
     re.compile(r"\b(tuna|beans|foul|lentils|sauce|ketchup|mayonnaise|تونة|فول|صلصة|كاتشب|مايونيز)\b", re.I)),
    ("dairy_cheese_eggs", "Dairy & Eggs", "Milk & Dairy",
     re.compile(r"\b(milk|dairy|حليب|لبن|رايب)\b", re.I)),
    ("dairy_cheese_eggs", "Dairy & Eggs", "Cheese",
     re.compile(r"\b(cheese|cheddar|mozzarella|feta|roumy|kiri|جبن|جبنة|موتزاريلا|شيدر|فيتا|رومي)\b", re.I)),
    ("dairy_cheese_eggs", "Dairy & Eggs", "Eggs & Butter",
     re.compile(r"\b(eggs?|butter|cream|بيض|زبدة|قشطة)\b", re.I)),
    ("beverages", "Hot Beverages", "Tea & Coffee",
     re.compile(r"\b(tea|coffee|nescafe|cappuccino|شاي|قهوة|نسكافيه)\b", re.I)),
    ("beverages", "Cold Beverages", "Water & Soft Drinks",
     re.compile(r"\b(mineral\s+water|juice|nectar|cola|soda|soft\s+drink|مياه\s+معدنية|عصير|كولا|صودا)\b", re.I)),
    ("bakery_snacks", "Bakery & Sweets", "Chocolate & Sweets",
     re.compile(r"\b(chocolate|candy|شوكولاتة|حلويات)\b", re.I)),
    ("bakery_snacks", "Bakery & Sweets", "Chips & Snacks",
     re.compile(r"\b(chips|crisps|popcorn|nuts|شيبسي|مقرمشات|مكسرات)\b", re.I)),
    ("bakery_snacks", "Bakery & Sweets", "Bakery & Biscuits",
     re.compile(r"\b(bread|toast|croissant|biscuit|cookie|wafer|خبز|عيش|توست|بسكويت|كوكيز|ويفر)\b", re.I)),
    ("fresh_meats_poultry", "Fresh Meat & Poultry", "Beef & Veal",
     re.compile(r"\b(meat|beef|veal|lamb|minced|steak|لحم|لحوم|لحمة|كندوز|بتلو|ضاني|مفروم|كفتة|سجق)\b", re.I)),
    ("fresh_meats_poultry", "Fresh Meat & Poultry", "Chicken & Poultry",
     re.compile(r"\b(poultry|chicken|duck|turkey|فراخ|دجاج|دواجن|بط|رومي|بانيه|شيش)\b", re.I)),
    ("fresh_meats_poultry", "Fresh Meat & Poultry", "Seafood & Fish",
     re.compile(r"\b(seafood|fish|shrimp|salmon|سمك|أسماك|جمبري|سلمون)\b", re.I)),
    ("fruits_vegetables", "Fresh Produce", "Fresh Vegetables",
     re.compile(r"\b(vegetable|tomato|potato|onion|garlic|cucumber|carrot|خضار|خضروات|طماطم|بطاطس|بصل|ثوم|خيار|جزر)\b", re.I)),
    ("fruits_vegetables", "Fresh Produce", "Fresh Fruits",
     re.compile(r"\b(fruit|apple\s+fruit|banana|orange|mango|فواكه|فاكهة|تفاح|موز|برتقال|مانجو|ليمون)\b", re.I)),
    ("frozen_foods", "Frozen Foods", "Frozen Foods",
     re.compile(r"\b(frozen|french\s+fries|ice\s+cream|nuggets|strips|مجمد|مجمدة|مجمدات|آيس\s+كريم|ناجتس|ستربس|بطاطس\s+نصف\s+مقلية)\b", re.I)),
    ("other", "Services & Support", "Warranty & Protection Plans",
     re.compile(r"\b(tradelinecare|applecare|warranty|ضمان|تأمين\s+اضافى|تأمين)\b", re.I)),
    ("other", "Vehicles & Mobility", "Electric Scooters & Mobility",
     re.compile(r"\b(scooter|سكوتر)\b", re.I)),
]

# Standard default categories and subcategories per canonical department
_DEPARTMENT_FALLBACKS: dict[str, tuple[str, str]] = {
    Department.MOBILES_TABLETS.value: ("Mobile Accessories", "Mobile Accessories & Other"),
    Department.COMPUTING.value: ("Computer Accessories", "Computer Accessories & Peripherals"),
    Department.ELECTRONICS_TV.value: ("Electronics & Audio", "Electronics & Audio Accessories"),
    Department.HOME_APPLIANCES.value: ("Small Kitchen Appliances", "Domestic Appliances & Kitchenware"),
    Department.PERSONAL_CARE_BEAUTY.value: ("Personal Care & Beauty", "Personal Care & Grooming"),
    Department.GROCERY_PANTRY.value: ("Pantry Staples", "Pantry Staples & Food Cupboard"),
    Department.HOUSEHOLD_CLEANING.value: ("Household & Cleaning", "Household & Cleaning Supplies"),
    Department.DAIRY_CHEESE_EGGS.value: ("Dairy & Eggs", "Dairy Products & Eggs"),
    Department.BEVERAGES.value: ("Beverages", "Beverages & Drinks"),
    Department.BAKERY_SNACKS.value: ("Bakery & Snacks", "Bakery & Sweet Snacks"),
    Department.FRESH_MEATS_POULTRY.value: ("Fresh Meats & Poultry", "Meats, Poultry & Fish"),
    Department.FRUITS_VEGETABLES.value: ("Fresh Produce", "Fruits & Vegetables"),
    Department.FROZEN_FOODS.value: ("Frozen Foods", "Frozen Products"),
    Department.OTHER.value: ("Other Categories", "General Products & Services"),
}


def classify_product(
    product_name: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    raw_category_path: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """
    Deterministically classify a product into:
        - department: canonical Department code (e.g. 'mobiles_tablets', 'electronics_tv', 'fresh_meats_poultry')
        - department_ar: Arabic department label
        - category: clean category name (never None)
        - subcategory: clean granular subcategory name (never None)
    """
    def _clean(text: str) -> str:
        t = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]", "", text)
        t = re.sub(r"([\u0600-\u06FF])([A-Za-z0-9])", r"\1 \2", t)
        t = re.sub(r"([A-Za-z0-9])([\u0600-\u06FF])", r"\1 \2", t)
        return t

    clean_name = _clean(str(product_name or ""))
    combined_text = _clean(
        " | ".join(str(x) for x in (raw_category_path, subcategory, category, product_name) if x)
    )

    detected_dept: Optional[str] = None
    default_cat: Optional[str] = None

    # 1a. Check specific keyword rules on product_name alone first so noisy page-level
    #     categories (e.g. 'Televisions & Electronics' on a Samsung phone) don't override title
    if clean_name:
        for dept_code, d_cat, pattern in _CLASSIFICATION_RULES:
            if pattern.search(clean_name):
                detected_dept = dept_code
                default_cat = d_cat
                break

    # 1b. Check keyword rules on combined_text (category path + product name)
    if not detected_dept:
        for dept_code, d_cat, pattern in _CLASSIFICATION_RULES:
            if pattern.search(combined_text):
                detected_dept = dept_code
                default_cat = d_cat
                break

    # 2. Check direct category key mapping
    if not detected_dept:
        for candidate in (subcategory, category):
            if candidate:
                ckey = candidate.strip().lower()
                if ckey in _DIRECT_CATEGORY_MAP:
                    detected_dept, default_cat = _DIRECT_CATEGORY_MAP[ckey]
                    break
                if ckey.startswith("mobiles"):
                    detected_dept = Department.MOBILES_TABLETS.value
                    default_cat = "Mobile Phones"
                    break

    # 3. Match granular subcategory rules
    inferred_subcat: Optional[str] = None
    inferred_cat: Optional[str] = None

    # First check if subcategory has breadcrumb notation (e.g. 'A > B > C')
    clean_subcat = str(subcategory or "").strip()
    if clean_subcat and " > " in clean_subcat:
        crumbs = [c.strip() for c in clean_subcat.split(" > ") if c.strip()]
        if crumbs:
            inferred_subcat = crumbs[-1]

    for rule_dept, r_cat, r_subcat, pattern in _SUBCATEGORY_RULES:
        if pattern.search(combined_text):
            if not inferred_subcat:
                inferred_subcat = r_subcat
            if not inferred_cat:
                inferred_cat = r_cat
            # If department was still unknown or OTHER, adopt rule's department
            if not detected_dept or detected_dept == Department.OTHER.value:
                detected_dept = rule_dept
            break

    # Fallback to OTHER if still unresolved
    dept_code = detected_dept or Department.OTHER.value
    meta = DEPARTMENT_CATALOG.get(dept_code, DEPARTMENT_CATALOG[Department.OTHER.value])
    fallback_cat, fallback_subcat = _DEPARTMENT_FALLBACKS.get(
        dept_code, ("Other Categories", "General Products & Services")
    )

    final_cat = category or inferred_cat or default_cat or fallback_cat
    if final_cat in ("Uncategorized", "", None):
        final_cat = inferred_cat or default_cat or fallback_cat

    final_subcat = inferred_subcat or subcategory or fallback_subcat

    return {
        "department": dept_code,
        "department_ar": meta["name_ar"],
        "category": final_cat,
        "subcategory": final_subcat,
    }
