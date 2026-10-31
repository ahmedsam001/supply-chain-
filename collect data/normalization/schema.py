"""
Canonical data models for the Egypt E-Commerce Data Platform.

All source extractors normalize their output into these Pydantic models.
This ensures a consistent schema regardless of the upstream source.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# ─── Enums ────────────────────────────────────────────────────────────

class ComplianceStatus(str, Enum):
    """Compliance classification for a data source."""
    ALLOWED = "A"                    # Clear evidence supports automated access
    CONDITIONAL = "B"                # Requires conditions / authorization
    DO_NOT_AUTOMATE = "C"            # Explicit prohibition
    UNKNOWN = "D"                    # Unable to determine


class ExtractionMethod(str, Enum):
    """Method used to extract data from the source."""
    OFFICIAL_API = "official_api"
    PUBLIC_JSON = "public_json"
    EMBEDDED_JSON_LD = "embedded_json_ld"
    STATIC_HTML = "static_html"
    PLAYWRIGHT = "playwright"


class AvailabilityStatus(str, Enum):
    """Product availability classification."""
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LIMITED_STOCK = "limited_stock"
    PRE_ORDER = "pre_order"
    DISCONTINUED = "discontinued"
    DELISTED = "delisted"
    UNKNOWN = "unknown"


class LocationType(str, Enum):
    """Type of physical or logical location."""
    STORE = "store"
    BRANCH = "branch"
    WAREHOUSE = "warehouse"
    PICKUP_POINT = "pickup_point"
    DELIVERY_ZONE = "delivery_zone"       # kept for backward compat (old JSON)
    DELIVERY_AREA = "delivery_area"       # canonical preferred name
    SERVICE_CENTER = "service_center"
    FULFILLMENT_CENTER = "fulfillment_center"
    PRESENCE = "presence"
    COVERAGE = "coverage"
    UNKNOWN = "unknown"


class Currency(str, Enum):
    """Supported currencies."""
    EGP = "EGP"
    USD = "USD"
    EUR = "EUR"


class AvailabilityScope(str, Enum):
    """Semantic scope of a product availability observation."""
    GLOBAL = "GLOBAL"                         # Online catalog only
    DELIVERY_AREA = "DELIVERY_AREA"            # Deliverable to area
    PHYSICAL_BRANCH = "PHYSICAL_BRANCH"        # Stocked at named branch
    CENTRAL_WAREHOUSE = "CENTRAL_WAREHOUSE"    # Central warehouse
    SELLER_NETWORK = "SELLER_NETWORK"          # Marketplace seller dependent
    UNKNOWN = "UNKNOWN"                        # Ambiguous


# ─── Issue Codes / Severity ───────────────────────────────────────────

class IssueCode(str, Enum):
    MISSING_FIELD = "MISSING_FIELD"
    DUPLICATE_PRODUCT = "DUPLICATE_PRODUCT"
    DUPLICATE_LISTING = "DUPLICATE_LISTING"
    DUPLICATE_OBSERVATION = "DUPLICATE_OBSERVATION"
    MULTIPLE_SELLERS = "MULTIPLE_SELLERS"
    MULTIPLE_VARIANTS = "MULTIPLE_VARIANTS"
    INVALID_PRICE = "INVALID_PRICE"
    PRICE_INCONSISTENCY = "PRICE_INCONSISTENCY"
    NON_EGP_CURRENCY = "NON_EGP_CURRENCY"
    INVALID_URL = "INVALID_URL"
    INCONSISTENT_CATEGORY = "INCONSISTENT_CATEGORY"
    INCONSISTENT_LOCATION_NAME = "INCONSISTENT_LOCATION_NAME"
    INVALID_COORDINATES = "INVALID_COORDINATES"
    OUT_OF_EGYPT_COORDINATES = "OUT_OF_EGYPT_COORDINATES"
    UNKNOWN_GOVERNORATE = "UNKNOWN_GOVERNORATE"
    SCOPE_SEMANTICS_VIOLATION = "SCOPE_SEMANTICS_VIOLATION"
    STOCK_QUANTITY_WITHOUT_EVIDENCE = "STOCK_QUANTITY_WITHOUT_EVIDENCE"
    AMBIGUOUS_AVAILABILITY = "AMBIGUOUS_AVAILABILITY"
    LOW_STOCK_SIGNAL_MISPARSE = "LOW_STOCK_SIGNAL_MISPARSE"
    INVALID_DISCOUNT = "INVALID_DISCOUNT"
    MISSING_SKU = "MISSING_SKU"
    IDENTIFIER_CHANGE = "IDENTIFIER_CHANGE"


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class DataQualityIssue(BaseModel):
    """Structured data quality issue detected during validation."""
    issue_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: Optional[str] = None
    source_id: str
    entity_type: str        # "product", "observation", "location"
    entity_id: str
    issue_code: IssueCode
    severity: IssueSeverity
    message: str
    raw_value: Optional[str] = None
    source_url: Optional[str] = None
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Source ───────────────────────────────────────────────────────────

class Source(BaseModel):
    """Represents an e-commerce data source."""
    source_id: str = Field(description="Unique identifier for the source")
    source_name: str = Field(description="Human-readable source name")
    domain: str = Field(description="Primary domain of the source")
    compliance_status: ComplianceStatus = Field(
        description="Legal compliance classification"
    )
    extraction_method: ExtractionMethod = Field(
        description="Primary extraction method"
    )
    last_verified_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When compliance was last verified"
    )
    rate_limit_rpm: int = Field(default=30, description="Max requests per minute")
    min_delay_seconds: float = Field(default=1.5, description="Min delay between requests")
    max_delay_seconds: float = Field(default=4.0, description="Max delay between requests")
    enabled: bool = Field(default=True, description="Whether extraction is enabled")
    notes: str = Field(default="", description="Additional notes")

    # Extended source metadata
    official_url: Optional[str] = None
    business_type: Optional[str] = None
    research_status: Optional[str] = None
    implementation_status: Optional[str] = None
    reason: Optional[str] = None
    evidence_url: Optional[str] = None
    evidence_captured_on: Optional[str] = None
    evidence_summary: Optional[str] = None
    evidence_decided_by: Optional[str] = None


# ─── Product ──────────────────────────────────────────────────────────

class Product(BaseModel):
    """Canonical product record — identity only, no price or stock."""
    product_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Internal unique product ID"
    )
    source_id: str = Field(description="Source this product belongs to")
    source_product_id: str = Field(description="ID as used by the source")
    sku: Optional[str] = Field(default=None, description="Stock-keeping unit")
    product_name: str = Field(description="Product display name")
    brand: Optional[str] = Field(default=None, description="Brand name")
    category: Optional[str] = Field(default=None, description="Top-level category")
    subcategory: Optional[str] = Field(default=None, description="Sub-category")
    product_url: str = Field(description="Full URL to the product page")
    image_url: Optional[str] = Field(default=None, description="Primary image URL")
    specifications: Optional[dict] = Field(
        default=None, description="Product specifications as key-value pairs"
    )

    # Extended product fields
    department: Optional[str] = Field(
        default=None,
        description="Canonical department code (e.g. mobiles_tablets, electronics_tv, fresh_meats_poultry)",
    )
    gtin: Optional[str] = Field(default=None, description="GTIN/EAN/barcode")
    raw_category_path: Optional[str] = Field(default=None, description="Original breadcrumb text")
    source_url: Optional[str] = Field(default=None, description="Canonical source URL")
    collected_at: Optional[datetime] = Field(default=None, description="When first collected")
    variants: Optional[list[dict]] = Field(default=None, description="Product variants if exposed")
    run_id: Optional[str] = Field(default=None, description="Extraction run ID")

    @field_validator("product_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("product_name must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def _populate_product_defaults(self) -> "Product":
        from normalization.normalizers import normalize_image_url
        if self.image_url:
            self.image_url = normalize_image_url(self.image_url)
        if self.source_url is None and self.product_url:
            self.source_url = self.product_url
        if self.collected_at is None:
            self.collected_at = datetime.now(timezone.utc)
        if self.department is None:
            from normalization.taxonomy import classify_product
            tax = classify_product(
                product_name=self.product_name,
                category=self.category,
                subcategory=self.subcategory,
                raw_category_path=self.raw_category_path,
            )
            self.department = tax["department"]
        return self


# ─── Location ─────────────────────────────────────────────────────────

class Location(BaseModel):
    """A physical store, warehouse, pickup point, or delivery zone."""
    location_id: str = Field(
        default="",
        description="Internal unique location ID (derived deterministically if omitted)"
    )
    source_id: str = Field(description="Source this location belongs to")
    location_type: LocationType = Field(description="Type of location")
    branch_name: Optional[str] = Field(default=None, description="Branch or store name")
    address: Optional[str] = Field(default=None, description="Full address text")
    city: Optional[str] = Field(default=None, description="City name")
    governorate: Optional[str] = Field(default=None, description="Egyptian governorate")
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    delivery_zone: Optional[str] = Field(default=None, description="Delivery zone name/code")
    phone: Optional[str] = Field(default=None, description="Contact phone")
    working_hours: Optional[str] = Field(default=None, description="Working hours text")

    # Extended location fields
    location_name: Optional[str] = Field(default=None, description="Canonical location name")
    warehouse_name: Optional[str] = Field(default=None, description="Warehouse identifier")
    district: Optional[str] = Field(default=None, description="District/area within city")
    raw_location_name: Optional[str] = Field(default=None, description="Raw name from source")
    source_url: Optional[str] = Field(default=None, description="URL of store locator page")
    collected_at: Optional[datetime] = Field(default=None, description="When collected")
    run_id: Optional[str] = Field(default=None, description="Extraction run ID")

    @model_validator(mode="after")
    def _populate_stable_location_id(self) -> "Location":
        if not self.location_id:
            from geospatial.egypt_geography import derive_location_id
            name = (
                self.branch_name
                or self.location_name
                or self.delivery_zone
                or self.governorate
                or self.city
                or "unnamed"
            )
            self.location_id = derive_location_id(
                source_id=self.source_id,
                location_type=self.location_type.value if hasattr(self.location_type, "value") else str(self.location_type),
                normalized_name=name,
                address=self.address,
            )
        if self.collected_at is None:
            self.collected_at = datetime.now(timezone.utc)
        return self


# ─── Product Observation ─────────────────────────────────────────────

class ProductObservation(BaseModel):
    """
    A point-in-time observation of a product's price and availability.
    This table is append-only — historical records are never deleted.
    """
    observation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique observation ID"
    )
    product_id: str = Field(description="FK to products table")
    location_id: Optional[str] = Field(
        default=None, description="FK to locations table (if location-specific)"
    )
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the observation"
    )
    price: Optional[float] = Field(default=None, ge=0, description="Current price")
    old_price: Optional[float] = Field(default=None, ge=0, description="Original / old price")
    discount: Optional[float] = Field(
        default=None, ge=0, le=100, description="Discount percentage"
    )
    currency: Currency = Field(default=Currency.EGP)
    availability_status: AvailabilityStatus = Field(default=AvailabilityStatus.UNKNOWN)
    delivery_status: Optional[str] = Field(
        default=None, description="Delivery info text (e.g., 'Next day delivery')"
    )
    rating: Optional[float] = Field(default=None, ge=0, le=5, description="Average rating")
    review_count: Optional[int] = Field(default=None, ge=0, description="Number of reviews")
    source_url: Optional[str] = Field(default=None, description="URL where data was observed")
    seller_name: Optional[str] = Field(default=None, description="Third-party seller name")
    sellers: Optional[list[str]] = Field(default=None, description="All seller names if multi-seller")

    # Extended observation fields
    source_id: Optional[str] = Field(default=None, description="Source identifier")
    source_product_id: Optional[str] = Field(default=None, description="Source's product id")
    collected_at: Optional[datetime] = Field(default=None, description="Alias for observed_at")
    stock_status: Optional[str] = Field(
        default=None, description="e.g. IN_STOCK, OUT_OF_STOCK, LOW_STOCK_SIGNAL, UNKNOWN"
    )
    stock_quantity: Optional[int] = Field(
        default=None, description="ONLY when source explicitly provides count"
    )
    stock_quantity_evidence: Optional[str] = Field(
        default=None, description="Where quantity came from"
    )
    raw_availability_text: Optional[str] = Field(
        default=None, description="Exact raw text from source"
    )
    raw_price_text: Optional[str] = Field(
        default=None, description="Exact raw price text from source"
    )
    availability_scope: AvailabilityScope = Field(
        default=AvailabilityScope.UNKNOWN,
        description="Semantic scope of availability"
    )
    fulfillment_method: Optional[str] = Field(
        default=None, description="marketplace/retailer-fulfilled/pickup/unknown"
    )
    delivery_available: Optional[bool] = Field(default=None)
    delivery_eta: Optional[str] = Field(default=None)
    delivery_fee: Optional[float] = Field(default=None)
    hash_version: int = Field(default=2, description="Row hash algorithm version")
    row_hash: Optional[str] = Field(default=None, description="Deterministic SHA-256 row hash")
    run_id: Optional[str] = Field(default=None, description="Extraction run ID")

    def compute_row_hash(self) -> str:
        """Deterministic hash for change detection (v2)."""
        payload = (
            f"{self.price}|{self.old_price}|{self.discount}|"
            f"{self.availability_status}|{self.delivery_status}|"
            f"{self.availability_scope}|{self.stock_status}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @model_validator(mode="after")
    def _populate_row_hash(self) -> "ProductObservation":
        from normalization.normalizers import (
            normalize_stock_status,
            normalize_availability_status,
        )
        self.stock_status = normalize_stock_status(self.stock_status, self.availability_status)
        if self.availability_status == AvailabilityStatus.UNKNOWN and self.stock_status != "UNKNOWN":
            norm_avail = normalize_availability_status(None, self.stock_status)
            try:
                self.availability_status = AvailabilityStatus(norm_avail)
            except Exception:
                pass
        self.row_hash = self.compute_row_hash()
        if self.collected_at is None:
            self.collected_at = self.observed_at
        return self


# ─── Extraction Result ────────────────────────────────────────────────

class ExtractionResult(BaseModel):
    """Container for a single extraction run's output."""
    source_id: str
    run_id: Optional[str] = None
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    products: list[Product] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    observations: list[ProductObservation] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    pages_visited: int = 0
    duration_seconds: float = 0.0
    quality_issues: list[DataQualityIssue] = Field(default_factory=list)
    mode: str = Field(default="live", description="live, offline_fixture, or synthetic")

    @property
    def success_rate(self) -> float:
        total = len(self.products) + len(self.errors)
        return len(self.products) / total if total > 0 else 0.0
