from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

import models


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=140)
    email: str
    phone: Optional[str] = Field(default=None, max_length=30)
    password: str = Field(..., min_length=4)


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=2)
    password: str = Field(..., min_length=4)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(..., min_length=20)


class GoogleConfigOut(BaseModel):
    client_id: str
    provider: str = "google"


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=140)
    phone: Optional[str] = Field(default=None, max_length=30)
    avatar_url: Optional[str] = None


class MenuItemIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=180)
    desc: Optional[str] = Field(default=None, max_length=255)
    price: str = Field(..., min_length=1, max_length=80)


class ProductIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=180)
    price_label: str = Field(..., min_length=1, max_length=80)
    price_amount: Optional[Decimal] = None
    image_url: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=120)
    short_description: Optional[str] = Field(default=None, max_length=255)


class ServiceIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=180)
    price_label: Optional[str] = Field(default=None, max_length=80)
    price_amount: Optional[Decimal] = None
    image_url: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=120)
    short_description: Optional[str] = Field(default=None, max_length=255)


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=180)
    company_type: models.CompanyType
    category: Optional[str] = Field(default=None, max_length=120)
    location: str = Field(..., min_length=2, max_length=180)
    district: Optional[str] = Field(default=None, max_length=180)
    description: Optional[str] = None
    short_description: Optional[str] = Field(default=None, max_length=300)
    phone: str = Field(..., min_length=5, max_length=30)
    email: Optional[str] = None
    whatsapp: Optional[str] = Field(default=None, max_length=30)
    website: Optional[str] = Field(default=None, max_length=255)
    instagram: Optional[str] = Field(default=None, max_length=255)
    facebook: Optional[str] = Field(default=None, max_length=255)
    logo_url: Optional[str] = None
    cover_url: Optional[str] = None

    stay_type: Optional[str] = Field(default=None, max_length=80)
    price_per_night: Optional[Decimal] = None
    currency: Optional[str] = Field(default="EUR", max_length=10)
    rating: Optional[Decimal] = None
    badge: Optional[str] = Field(default=None, max_length=120)
    amenities: List[str] = Field(default_factory=list)

    host_name: Optional[str] = Field(default=None, max_length=180)
    schedule_text: Optional[str] = Field(default=None, max_length=180)
    category_label: Optional[str] = Field(default=None, max_length=120)

    cuisine: Optional[str] = Field(default=None, max_length=120)
    signature: Optional[str] = Field(default=None, max_length=180)
    menu_items: List[MenuItemIn] = Field(default_factory=list)

    area: Optional[str] = Field(default=None, max_length=120)
    sales_count: int = 0
    story_quote: Optional[str] = Field(default=None, max_length=400)
    social_links: List[dict] = Field(default_factory=list)
    products: List[ProductIn] = Field(default_factory=list)
    services: List[ServiceIn] = Field(default_factory=list)

    @field_validator("company_type", mode="before")
    @classmethod
    def normalize_company_type(cls, value: object) -> object:
        if isinstance(value, models.CompanyType):
            return value
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        aliases = {
            "alojamento": models.CompanyType.LODGING,
            "beach": models.CompanyType.BEACH,
            "experiencia": models.CompanyType.EXPERIENCE,
            "experiência": models.CompanyType.EXPERIENCE,
            "fornecedor": models.CompanyType.SUPPLIER,
            "hotelaria": models.CompanyType.HOSPITALITY,
            "praia": models.CompanyType.BEACH,
            "praias": models.CompanyType.BEACH,
            "producer": models.CompanyType.PRODUCER,
            "produtor": models.CompanyType.PRODUCER,
            "restaurant": models.CompanyType.RESTAURANT,
            "restaurante": models.CompanyType.RESTAURANT,
            "restauracao": models.CompanyType.RESTAURANT,
            "restauração": models.CompanyType.RESTAURANT,
            "service": models.CompanyType.SERVICE,
            "servico": models.CompanyType.SERVICE,
            "serviço": models.CompanyType.SERVICE,
            "servicos": models.CompanyType.SERVICE,
            "serviços": models.CompanyType.SERVICE,
            "supplier": models.CompanyType.SUPPLIER,
            "hospitality": models.CompanyType.HOSPITALITY,
            "lodging": models.CompanyType.LODGING,
        }
        return aliases.get(normalized, normalized)


class CompanySignupRequest(BaseModel):
    user: UserCreate
    company: CompanyCreate


class CompanySummary(BaseModel):
    id: int
    name: str
    slug: str
    company_type: str
    category: Optional[str] = None
    location: str
    phone: str
    status: str
    is_verified: bool
    is_featured: bool
    created_at: datetime


class CompanyOut(CompanySummary):
    district: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    website: Optional[str] = None
    instagram: Optional[str] = None
    facebook: Optional[str] = None
    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    owner_user_id: int
    updated_at: datetime


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=180)
    category: Optional[str] = Field(default=None, max_length=120)
    location: Optional[str] = Field(default=None, min_length=2, max_length=180)
    district: Optional[str] = Field(default=None, max_length=180)
    description: Optional[str] = None
    short_description: Optional[str] = Field(default=None, max_length=300)
    phone: Optional[str] = Field(default=None, min_length=5, max_length=30)
    email: Optional[str] = None
    whatsapp: Optional[str] = Field(default=None, max_length=30)
    website: Optional[str] = Field(default=None, max_length=255)
    instagram: Optional[str] = Field(default=None, max_length=255)
    facebook: Optional[str] = Field(default=None, max_length=255)
    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    status: Optional[str] = None
    is_featured: Optional[bool] = None


class LodgingProfileUpdate(BaseModel):
    stay_type: Optional[str] = Field(default=None, max_length=80)
    price_per_night: Optional[Decimal] = None
    currency: Optional[str] = Field(default=None, max_length=10)
    rating: Optional[Decimal] = None
    badge: Optional[str] = Field(default=None, max_length=120)
    amenities: Optional[List[str]] = None


class ExperienceProfileUpdate(BaseModel):
    host_name: Optional[str] = Field(default=None, max_length=180)
    schedule_text: Optional[str] = Field(default=None, max_length=180)
    badge: Optional[str] = Field(default=None, max_length=120)
    category_label: Optional[str] = Field(default=None, max_length=120)


class RestaurantProfileUpdate(BaseModel):
    cuisine: Optional[str] = Field(default=None, max_length=120)
    signature: Optional[str] = Field(default=None, max_length=180)
    rating: Optional[Decimal] = None


class ProducerProfileUpdate(BaseModel):
    area: Optional[str] = Field(default=None, max_length=120)
    rating: Optional[Decimal] = None
    sales_count: Optional[int] = None
    story_quote: Optional[str] = Field(default=None, max_length=400)
    social_links: Optional[List[dict]] = None


class AuthMeOut(BaseModel):
    user: UserOut
    companies: List[CompanySummary]


class CompanyTypeOption(BaseModel):
    code: str
    label: str
    supports_products: bool = False
    supports_services: bool = True


class FavoriteToggleRequest(BaseModel):
    target_type: str
    company_id: Optional[int] = None
    product_id: Optional[int] = None


class FavoriteOut(BaseModel):
    id: int
    target_type: str
    company_id: Optional[int] = None
    product_id: Optional[int] = None
    created_at: datetime


class FavoriteCollectionOut(BaseModel):
    companies: List[CompanySummary] = []
    products: List["MarketProductOut"] = []


class CompanySocialState(BaseModel):
    company_id: int
    likes_count: int
    followers_count: int
    comments_count: int
    liked_by_me: bool = False
    following_by_me: bool = False


class CompanyCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class CompanyCommentOut(BaseModel):
    id: int
    company_id: int
    user_id: int
    user_name: str
    user_avatar_url: Optional[str] = None
    content: str
    created_at: datetime
    updated_at: datetime


class LeadCreate(BaseModel):
    lead_type: str = Field(default="contact")
    customer_name: str = Field(..., min_length=2, max_length=180)
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = Field(default=None, max_length=30)
    message: Optional[str] = None
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    guests_count: Optional[int] = None
    service_name: Optional[str] = None
    product_name: Optional[str] = None
    quantity: Optional[int] = None


class LeadUpdate(BaseModel):
    status: str
    admin_notes: Optional[str] = None


class LeadOut(BaseModel):
    id: int
    company_id: int
    requester_user_id: Optional[int] = None
    lead_type: str
    status: str
    customer_name: str
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    message: Optional[str] = None
    admin_notes: Optional[str] = None
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    guests_count: Optional[int] = None
    service_name: Optional[str] = None
    product_name: Optional[str] = None
    quantity: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class SeloRequestCreate(BaseModel):
    motivation: Optional[str] = None
    documents: List[dict] = Field(default_factory=list)


class SeloRequestReview(BaseModel):
    status: str
    admin_notes: Optional[str] = None


class SeloRequestOut(BaseModel):
    id: int
    company_id: int
    requested_by_user_id: Optional[int] = None
    status: str
    motivation: Optional[str] = None
    documents: List[dict] = Field(default_factory=list)
    admin_notes: Optional[str] = None
    reviewed_by_user_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class NotificationOut(BaseModel):
    id: int
    user_id: int
    notification_type: str
    title: str
    body: Optional[str] = None
    payload: Optional[dict] = None
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationReadUpdate(BaseModel):
    is_read: bool = True


class LodgingSummary(BaseModel):
    id: int
    name: str
    slug: str
    location: str
    price: Decimal
    currency: str
    rating: Optional[Decimal] = None
    image: Optional[str] = None
    badge: Optional[str] = None
    type: str
    short_description: Optional[str] = None


class LodgingDetail(LodgingSummary):
    description: Optional[str] = None
    amenities: List[str] = []
    services: List["CompanyServiceOut"] = []


class ExperienceSummary(BaseModel):
    id: int
    name: str
    slug: str
    host: str
    location: str
    date: Optional[str] = None
    image: Optional[str] = None
    badge: Optional[str] = None
    category: Optional[str] = None
    short_description: Optional[str] = None


class ExperienceDetail(ExperienceSummary):
    description: Optional[str] = None
    services: List["CompanyServiceOut"] = []


class RestaurantSummary(BaseModel):
    id: int
    name: str
    slug: str
    location: str
    rating: Optional[Decimal] = None
    likes: int
    image: Optional[str] = None
    cuisine: Optional[str] = None
    signature: Optional[str] = None
    short_description: Optional[str] = None


class RestaurantMenuItem(BaseModel):
    name: str
    desc: Optional[str] = None
    price: str


class RestaurantDetail(RestaurantSummary):
    description: Optional[str] = None
    menu: List[RestaurantMenuItem] = []
    services: List["CompanyServiceOut"] = []


class ProducerProductOut(BaseModel):
    id: int
    name: str
    price: str
    price_amount: Optional[Decimal] = None
    image: Optional[str] = None
    category: Optional[str] = None
    short_description: Optional[str] = None


class CompanyServiceOut(BaseModel):
    id: int
    name: str
    price_label: Optional[str] = None
    price_amount: Optional[Decimal] = None
    image: Optional[str] = None
    category: Optional[str] = None
    short_description: Optional[str] = None


class ProducerSummary(BaseModel):
    id: int
    name: str
    slug: str
    area: str
    location: str
    bio: Optional[str] = None
    image: Optional[str] = None
    cover: Optional[str] = None
    rating: Optional[Decimal] = None
    sales: int
    verified: bool
    story_quote: Optional[str] = None


class ProducerDetail(ProducerSummary):
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    links: List[dict] = []
    products: List[ProducerProductOut] = []
    services: List[CompanyServiceOut] = []


class MarketProductOut(BaseModel):
    id: int
    name: str
    price: str
    price_amount: Optional[Decimal] = None
    image: Optional[str] = None
    category: Optional[str] = None
    producer: ProducerSummary


class HomeResponse(BaseModel):
    lodgings: List[LodgingSummary]
    experiences: List[ExperienceSummary]
    restaurants: List[RestaurantSummary]
    producers: List[ProducerSummary]


class CategoryGroupOut(BaseModel):
    key: str
    label: str
    count: int


class SearchResultItem(BaseModel):
    entity_type: str
    id: int
    slug: str
    title: str
    subtitle: Optional[str] = None
    image: Optional[str] = None
    category: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    items: List[SearchResultItem]


class FeedItemOut(BaseModel):
    entity_type: str
    id: int
    slug: str
    title: str
    subtitle: Optional[str] = None
    image: Optional[str] = None
    category: Optional[str] = None


class ProfileSummaryOut(BaseModel):
    user: UserOut
    companies: List[CompanySummary] = []
    favorites_count: int = 0
    bookings_count: int = 0


class SellerDashboardOut(BaseModel):
    company: CompanyOut
    products: List[ProducerProductOut] = []
    services: List[CompanyServiceOut] = []
    leads: List[LeadOut] = []
    selo_requests: List[SeloRequestOut] = []


class AIChatMessage(BaseModel):
    role: str = "user"
    content: str = Field(..., min_length=1, max_length=8000)


class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[AIChatMessage] = Field(default_factory=list)


class AIChatResponse(BaseModel):
    reply: str
    model: str
