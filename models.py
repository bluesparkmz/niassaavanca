from datetime import datetime
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    DECIMAL,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    PARTNER = "partner"
    ADMIN = "admin"


class CompanyType(str, enum.Enum):
    HOSPITALITY = "hospitality"
    LODGING = "lodging"
    EXPERIENCE = "experience"
    RESTAURANT = "restaurant"
    PRODUCER = "producer"
    SUPPLIER = "supplier"
    BEACH = "beach"
    SERVICE = "service"


class CompanyStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FavoriteTargetType(str, enum.Enum):
    COMPANY = "company"
    PRODUCT = "product"


class LeadType(str, enum.Enum):
    BOOKING = "booking"
    QUOTE = "quote"
    CONTACT = "contact"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    REJECTED = "rejected"


class SeloStatus(str, enum.Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class NotificationType(str, enum.Enum):
    LEAD_CREATED = "lead_created"
    LEAD_UPDATED = "lead_updated"
    SELO_REQUEST_CREATED = "selo_request_created"
    SELO_REQUEST_REVIEWED = "selo_request_reviewed"
    SYSTEM = "system"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(140), nullable=False)
    email = Column(String(140), unique=True, index=True, nullable=False)
    phone = Column(String(30), unique=True, index=True, nullable=True)
    avatar_url = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
        default=UserRole.CUSTOMER,
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    companies = relationship("Company", back_populates="owner", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    leads = relationship("PartnerLead", back_populates="requester")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(180), nullable=False)
    slug = Column(String(180), unique=True, index=True, nullable=False)
    company_type = Column(
        Enum(CompanyType, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
    )
    category = Column(String(120), nullable=True, index=True)
    location = Column(String(180), nullable=False, index=True)
    district = Column(String(180), nullable=True)
    description = Column(Text, nullable=True)
    short_description = Column(String(300), nullable=True)
    phone = Column(String(30), nullable=False)
    email = Column(String(140), nullable=True)
    whatsapp = Column(String(30), nullable=True)
    website = Column(String(255), nullable=True)
    instagram = Column(String(255), nullable=True)
    facebook = Column(String(255), nullable=True)
    logo_url = Column(String(255), nullable=True)
    cover_url = Column(String(255), nullable=True)
    status = Column(
        Enum(CompanyStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
        default=CompanyStatus.PENDING,
    )
    is_verified = Column(Boolean, nullable=False, default=False)
    is_featured = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="companies")
    lodging_profile = relationship("LodgingProfile", back_populates="company", uselist=False, cascade="all, delete-orphan")
    experience_profile = relationship("ExperienceProfile", back_populates="company", uselist=False, cascade="all, delete-orphan")
    restaurant_profile = relationship("RestaurantProfile", back_populates="company", uselist=False, cascade="all, delete-orphan")
    producer_profile = relationship("ProducerProfile", back_populates="company", uselist=False, cascade="all, delete-orphan")
    services = relationship("CompanyService", back_populates="company", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="company")
    leads = relationship("PartnerLead", back_populates="company", cascade="all, delete-orphan")
    selo_requests = relationship("SeloNiassaRequest", back_populates="company", cascade="all, delete-orphan")


class LodgingProfile(Base):
    __tablename__ = "lodging_profiles"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    stay_type = Column(String(80), nullable=False, default="Lodge")
    price_per_night = Column(DECIMAL(14, 2), nullable=False, default=0.00)
    currency = Column(String(10), nullable=False, default="EUR")
    rating = Column(DECIMAL(4, 2), nullable=True)
    badge = Column(String(120), nullable=True)
    amenities = Column(JSON, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="lodging_profile")


class ExperienceProfile(Base):
    __tablename__ = "experience_profiles"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    host_name = Column(String(180), nullable=False)
    schedule_text = Column(String(180), nullable=True)
    badge = Column(String(120), nullable=True)
    category_label = Column(String(120), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="experience_profile")


class RestaurantProfile(Base):
    __tablename__ = "restaurant_profiles"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    cuisine = Column(String(120), nullable=True)
    signature = Column(String(180), nullable=True)
    likes_count = Column(Integer, nullable=False, default=0)
    rating = Column(DECIMAL(4, 2), nullable=True)
    menu_items = Column(JSON, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="restaurant_profile")


class ProducerProfile(Base):
    __tablename__ = "producer_profiles"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    area = Column(String(120), nullable=False, index=True)
    rating = Column(DECIMAL(4, 2), nullable=True)
    sales_count = Column(Integer, nullable=False, default=0)
    story_quote = Column(String(400), nullable=True)
    social_links = Column(JSON, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="producer_profile")
    products = relationship("ProducerProduct", back_populates="producer", cascade="all, delete-orphan")


class ProducerProduct(Base):
    __tablename__ = "producer_products"
    __table_args__ = (
        UniqueConstraint("producer_id", "name", name="uq_producer_product_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    producer_id = Column(Integer, ForeignKey("producer_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(180), nullable=False)
    price_label = Column(String(80), nullable=False)
    price_amount = Column(DECIMAL(14, 2), nullable=True)
    image_url = Column(String(255), nullable=True)
    category = Column(String(120), nullable=True, index=True)
    short_description = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    producer = relationship("ProducerProfile", back_populates="products")


class CompanyService(Base):
    __tablename__ = "company_services"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_company_service_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(180), nullable=False)
    price_label = Column(String(80), nullable=True)
    price_amount = Column(DECIMAL(14, 2), nullable=True)
    image_url = Column(String(255), nullable=True)
    category = Column(String(120), nullable=True, index=True)
    short_description = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="services")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "company_id", "product_id", name="uq_user_favorite_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type = Column(
        Enum(FavoriteTargetType, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
    )
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("producer_products.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="favorites")
    company = relationship("Company", back_populates="favorites")
    product = relationship("ProducerProduct")


class PartnerLead(Base):
    __tablename__ = "partner_leads"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    requester_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_type = Column(
        Enum(LeadType, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
        default=LeadType.CONTACT,
    )
    status = Column(
        Enum(LeadStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
        default=LeadStatus.NEW,
    )
    customer_name = Column(String(180), nullable=False)
    customer_email = Column(String(140), nullable=True)
    customer_phone = Column(String(30), nullable=True)
    message = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    check_in_date = Column(String(40), nullable=True)
    check_out_date = Column(String(40), nullable=True)
    guests_count = Column(Integer, nullable=True)
    service_name = Column(String(180), nullable=True)
    product_name = Column(String(180), nullable=True)
    quantity = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="leads")
    requester = relationship("User", back_populates="leads")


class SeloNiassaRequest(Base):
    __tablename__ = "selo_niassa_requests"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(
        Enum(SeloStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
        default=SeloStatus.PENDING,
    )
    motivation = Column(Text, nullable=True)
    documents = Column(JSON, nullable=True)
    admin_notes = Column(Text, nullable=True)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="selo_requests")
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type = Column(
        Enum(NotificationType, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
        default=NotificationType.SYSTEM,
    )
    title = Column(String(180), nullable=False)
    body = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    read_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="notifications")
