from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import models
import schemmas
from auth import create_access_token, get_current_user, get_password_hash, verify_password
from database import get_db


router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(text: str) -> str:
    return "-".join(text.strip().lower().split())


def _ensure_unique_user(db: Session, email: str, phone: str | None) -> None:
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="Email ja existe")
    if phone and db.query(models.User).filter(models.User.phone == phone).first():
        raise HTTPException(status_code=400, detail="Telefone ja existe")


def _ensure_unique_slug(db: Session, slug: str) -> str:
    final_slug = slug
    index = 2
    while db.query(models.Company).filter(models.Company.slug == final_slug).first():
        final_slug = f"{slug}-{index}"
        index += 1
    return final_slug


def _create_company_profile(db: Session, company: models.Company, payload: schemmas.CompanyCreate) -> None:
    company_type = payload.company_type.strip().lower()
    if company_type in {models.CompanyType.LODGING.value, models.CompanyType.HOSPITALITY.value, models.CompanyType.BEACH.value}:
        db.add(
            models.LodgingProfile(
                company_id=company.id,
                stay_type=payload.stay_type or "Lodge",
                price_per_night=payload.price_per_night or 0,
                currency=payload.currency or "EUR",
                rating=payload.rating,
                badge=payload.badge,
                amenities=payload.amenities or [],
            )
        )
    elif company_type == models.CompanyType.EXPERIENCE.value:
        db.add(
            models.ExperienceProfile(
                company_id=company.id,
                host_name=payload.host_name or company.name,
                schedule_text=payload.schedule_text,
                badge=payload.badge,
                category_label=payload.category_label or payload.category or "Experiência",
            )
        )
    elif company_type == models.CompanyType.RESTAURANT.value:
        db.add(
            models.RestaurantProfile(
                company_id=company.id,
                cuisine=payload.cuisine,
                signature=payload.signature,
                rating=payload.rating,
                menu_items=[item.model_dump() for item in payload.menu_items],
            )
        )
    elif company_type in {models.CompanyType.PRODUCER.value, models.CompanyType.SUPPLIER.value}:
        producer = models.ProducerProfile(
            company_id=company.id,
            area=payload.area or payload.category or "Produtor",
            rating=payload.rating,
            sales_count=payload.sales_count,
            story_quote=payload.story_quote,
            social_links=payload.social_links or [],
        )
        db.add(producer)
        db.flush()
        for item in payload.products:
            db.add(
                models.ProducerProduct(
                    producer_id=producer.id,
                    name=item.name,
                    price_label=item.price_label,
                    price_amount=item.price_amount,
                    image_url=item.image_url,
                    category=item.category,
                    short_description=item.short_description,
                )
            )
    for item in payload.services:
        db.add(
            models.CompanyService(
                company_id=company.id,
                name=item.name,
                price_label=item.price_label,
                price_amount=item.price_amount,
                image_url=item.image_url,
                category=item.category,
                short_description=item.short_description,
            )
        )


def _build_company_summary(company: models.Company) -> schemmas.CompanySummary:
    return schemmas.CompanySummary(
        id=company.id,
        name=company.name,
        slug=company.slug,
        company_type=company.company_type.value if hasattr(company.company_type, "value") else str(company.company_type),
        category=company.category,
        location=company.location,
        phone=company.phone,
        status=company.status.value if hasattr(company.status, "value") else str(company.status),
        is_verified=company.is_verified,
        is_featured=company.is_featured,
        created_at=company.created_at,
    )


def _build_auth_me(user: models.User) -> schemmas.AuthMeOut:
    return schemmas.AuthMeOut(
        user=schemmas.UserOut.model_validate(user),
        companies=[_build_company_summary(company) for company in user.companies],
    )


def _authenticate(db: Session, identifier: str, password: str) -> models.User | None:
    user = (
        db.query(models.User)
        .filter((models.User.email == identifier) | (models.User.phone == identifier))
        .first()
    )
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


@router.post("/register", response_model=schemmas.UserOut, status_code=status.HTTP_201_CREATED)
def register_user(payload: schemmas.UserCreate, db: Session = Depends(get_db)):
    _ensure_unique_user(db, payload.email, payload.phone)
    user = models.User(
        full_name=payload.full_name.strip(),
        email=payload.email.lower().strip(),
        phone=(payload.phone or "").strip() or None,
        password_hash=get_password_hash(payload.password),
        role=models.UserRole.CUSTOMER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/company-signup", response_model=schemmas.AuthMeOut, status_code=status.HTTP_201_CREATED)
def register_company(payload: schemmas.CompanySignupRequest, db: Session = Depends(get_db)):
    _ensure_unique_user(db, payload.user.email, payload.user.phone)

    user = models.User(
        full_name=payload.user.full_name.strip(),
        email=payload.user.email.lower().strip(),
        phone=(payload.user.phone or "").strip() or None,
        password_hash=get_password_hash(payload.user.password),
        role=models.UserRole.PARTNER,
    )
    db.add(user)
    db.flush()

    company_slug = _ensure_unique_slug(db, _slugify(payload.company.name))
    company = models.Company(
        owner_user_id=user.id,
        name=payload.company.name.strip(),
        slug=company_slug,
        company_type=payload.company.company_type.strip().lower(),
        category=payload.company.category,
        location=payload.company.location.strip(),
        district=payload.company.district,
        description=payload.company.description,
        short_description=payload.company.short_description,
        phone=payload.company.phone.strip(),
        email=str(payload.company.email) if payload.company.email else None,
        whatsapp=payload.company.whatsapp,
        website=payload.company.website,
        instagram=payload.company.instagram,
        facebook=payload.company.facebook,
        logo_url=payload.company.logo_url,
        cover_url=payload.company.cover_url,
        status=models.CompanyStatus.PENDING,
        is_verified=False,
        is_featured=False,
    )
    db.add(company)
    db.flush()
    _create_company_profile(db, company, payload.company)

    db.commit()
    db.refresh(user)
    return _build_auth_me(user)


@router.post("/login", response_model=schemmas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = _authenticate(db, form_data.username.strip(), form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    return schemmas.Token(access_token=create_access_token({"sub": user.id}))


@router.post("/login-json", response_model=schemmas.Token)
def login_json(payload: schemmas.LoginRequest, db: Session = Depends(get_db)):
    user = _authenticate(db, payload.identifier.strip(), payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    return schemmas.Token(access_token=create_access_token({"sub": user.id}))


@router.get("/me", response_model=schemmas.AuthMeOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return _build_auth_me(current_user)


@router.put("/me", response_model=schemmas.UserOut)
def update_me(
    payload: schemmas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)
    if "phone" in data and data["phone"]:
        exists = (
            db.query(models.User)
            .filter(models.User.phone == data["phone"], models.User.id != current_user.id)
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="Telefone ja existe")
    for key, value in data.items():
        setattr(current_user, key, value)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/profile", response_model=schemmas.ProfileSummaryOut)
def get_profile_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    favorites_count = db.query(models.Favorite).filter(models.Favorite.user_id == current_user.id).count()
    bookings_count = (
        db.query(models.PartnerLead)
        .filter(
            models.PartnerLead.requester_user_id == current_user.id,
            models.PartnerLead.lead_type == models.LeadType.BOOKING.value,
        )
        .count()
    )
    companies = [
        _build_company_summary(company)
        for company in db.query(models.Company).filter(models.Company.owner_user_id == current_user.id).all()
    ]
    return schemmas.ProfileSummaryOut(
        user=schemmas.UserOut.model_validate(current_user),
        companies=companies,
        favorites_count=favorites_count,
        bookings_count=bookings_count,
    )


@router.get("/company-types", response_model=list[schemmas.CompanyTypeOption])
def list_company_types():
    return [
        schemmas.CompanyTypeOption(code="producer", label="Produtor", supports_products=True, supports_services=True),
        schemmas.CompanyTypeOption(code="supplier", label="Fornecedor", supports_products=True, supports_services=True),
        schemmas.CompanyTypeOption(code="hospitality", label="Hotelaria", supports_products=False, supports_services=True),
        schemmas.CompanyTypeOption(code="lodging", label="Alojamento", supports_products=False, supports_services=True),
        schemmas.CompanyTypeOption(code="restaurant", label="Restaurante", supports_products=False, supports_services=True),
        schemmas.CompanyTypeOption(code="experience", label="Experiência", supports_products=False, supports_services=True),
        schemmas.CompanyTypeOption(code="beach", label="Praias", supports_products=False, supports_services=True),
        schemmas.CompanyTypeOption(code="service", label="Serviços", supports_products=False, supports_services=True),
    ]
