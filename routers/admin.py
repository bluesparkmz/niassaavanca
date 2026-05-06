from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import models
import schemmas
from auth import get_current_user, get_password_hash
from database import get_db
from routers.companies import (
    _company_out,
    _company_type_value,
    _create_company_profile,
    _ensure_company_profiles_for_type,
    _ensure_unique_slug,
    _slugify,
)


router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role != models.UserRole.ADMIN.value and not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Apenas admin")
    return current_user


def _normalize_username(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:32] or "utilizador"


def _ensure_unique_username(db: Session, username: str) -> str:
    base_username = _normalize_username(username)
    candidate = base_username
    index = 2
    while db.query(models.User).filter(models.User.username == candidate).first():
        candidate = f"{base_username}_{index}"
        index += 1
    return candidate


def _generate_password(length: int = 8) -> str:
    import string
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _get_or_create_owner_user(
    db: Session,
    email: str,
    full_name: str | None,
    phone: str | None,
) -> tuple[models.User, str | None]:
    normalized_email = email.lower().strip()
    user = db.query(models.User).filter(models.User.email == normalized_email).first()
    if user:
        return user, None

    generated_password = _generate_password(8)
    username_seed = normalized_email.split("@")[0]

    user = models.User(
        name=(full_name or username_seed).strip(),
        username=_ensure_unique_username(db, username_seed),
        full_name=(full_name or username_seed).strip(),
        email=normalized_email,
        phone=(phone or "").strip() or None,
        password_hash=get_password_hash(generated_password),
        role=models.UserRole.PARTNER,
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.flush()
    return user, generated_password


class AdminOwnerIn(BaseModel):
    email: str = Field(..., max_length=140)
    full_name: str | None = Field(default=None, max_length=140)
    phone: str | None = Field(default=None, max_length=30)


class AdminCreateCompanyIn(BaseModel):
    owner: AdminOwnerIn
    company: schemmas.CompanyCreate


class AdminCreateCompanyOut(BaseModel):
    owner_user: schemmas.UserOut
    company: schemmas.CompanyOut
    owner_temp_password: str
    is_new_user: bool = True


@router.post("/companies", response_model=AdminCreateCompanyOut, status_code=status.HTTP_201_CREATED)
def admin_create_company(
    payload: AdminCreateCompanyIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    owner, temp_password = _get_or_create_owner_user(
        db,
        email=str(payload.owner.email),
        full_name=payload.owner.full_name,
        phone=payload.owner.phone,
    )

    company_slug = _ensure_unique_slug(db, _slugify(payload.company.name))
    company = models.Company(
        owner_user_id=owner.id,
        name=payload.company.name.strip(),
        slug=company_slug,
        company_type=_company_type_value(payload.company),
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
    db.refresh(company)
    db.refresh(owner)

    return AdminCreateCompanyOut(
        owner_user=schemmas.UserOut.model_validate(owner),
        company=_company_out(company),
        owner_temp_password=temp_password or "",
        is_new_user=temp_password is not None,
    )


@router.get("/companies", response_model=list[schemmas.CompanyOut])
def admin_list_companies(
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    companies = db.query(models.Company).all()
    return [_company_out(company) for company in companies]


@router.get("/check-admin")
def check_admin(db: Session = Depends(get_db)):
    ADMIN_EMAIL = "djoaquimnamueto@gmail.com"
    user = db.query(models.User).filter(models.User.email == ADMIN_EMAIL.lower().strip()).first()
    if not user:
        return {"exists": False, "email": ADMIN_EMAIL}
    return {
        "exists": True,
        "email": user.email,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "is_admin": user.is_admin,
        "is_active": user.is_active,
    }


@router.patch("/companies/{company_id}", response_model=schemmas.CompanyOut)
def admin_update_company(
    company_id: int,
    payload: schemmas.CompanyUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")

    data = payload.model_dump(exclude_unset=True)
    new_company_type = data.get("company_type")
    for key, value in data.items():
        setattr(company, key, value)

    if new_company_type is not None:
        company_type_value = new_company_type.value if hasattr(new_company_type, "value") else str(new_company_type)
        _ensure_company_profiles_for_type(db, company, company_type_value)

    db.commit()
    db.refresh(company)
    return _company_out(company)


# --------------- Stats ---------------

@router.get("/stats")
def admin_stats(
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    total_users = db.query(func.count(models.User.id)).scalar() or 0
    total_companies = db.query(func.count(models.Company.id)).scalar() or 0
    total_products = db.query(func.count(models.ProducerProduct.id)).scalar() or 0
    total_services = db.query(func.count(models.CompanyService.id)).scalar() or 0
    total_leads = db.query(func.count(models.PartnerLead.id)).scalar() or 0
    pending_companies = (
        db.query(func.count(models.Company.id))
        .filter(models.Company.status == models.CompanyStatus.PENDING)
        .scalar()
        or 0
    )
    approved_companies = (
        db.query(func.count(models.Company.id))
        .filter(models.Company.status == models.CompanyStatus.APPROVED)
        .scalar()
        or 0
    )
    companies_by_type = (
        db.query(models.Company.company_type, func.count(models.Company.id))
        .group_by(models.Company.company_type)
        .all()
    )
    return {
        "total_users": total_users,
        "total_companies": total_companies,
        "total_products": total_products,
        "total_services": total_services,
        "total_leads": total_leads,
        "pending_companies": pending_companies,
        "approved_companies": approved_companies,
        "companies_by_type": {
            (t.value if hasattr(t, "value") else str(t)): c for t, c in companies_by_type
        },
    }


# --------------- Users ---------------

@router.get("/users")
def admin_list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    result = []
    for u in users:
        company_count = db.query(func.count(models.Company.id)).filter(models.Company.owner_user_id == u.id).scalar() or 0
        result.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "role": u.role.value if hasattr(u.role, "value") else str(u.role),
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "companies_count": company_count,
        })
    return result


@router.get("/users/{user_id}")
def admin_get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador nao encontrado")
    companies = db.query(models.Company).filter(models.Company.owner_user_id == user.id).all()
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "companies": [_company_out(c) for c in companies],
    }


# --------------- Company detail with products/services ---------------

@router.get("/companies/{company_id}/detail")
def admin_company_detail(
    company_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    company = (
        db.query(models.Company)
        .options(
            joinedload(models.Company.owner),
            joinedload(models.Company.services),
            joinedload(models.Company.producer_profile),
            joinedload(models.Company.restaurant_profile),
            joinedload(models.Company.lodging_profile),
        )
        .filter(models.Company.id == company_id)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")

    products = []
    if company.producer_profile:
        for p in company.producer_profile.products:
            products.append({
                "id": p.id,
                "name": p.name,
                "price_label": p.price_label,
                "price_amount": str(p.price_amount) if p.price_amount else None,
                "image_url": p.image_url,
                "category": p.category,
                "short_description": p.short_description,
                "active": p.active,
            })

    services = []
    for s in company.services:
        services.append({
            "id": s.id,
            "name": s.name,
            "price_label": s.price_label,
            "price_amount": str(s.price_amount) if s.price_amount else None,
            "image_url": s.image_url,
            "category": s.category,
            "short_description": s.short_description,
            "active": s.active,
        })

    rooms = []
    if company.lodging_profile:
        for r in company.lodging_profile.rooms:
            rooms.append({
                "id": r.id,
                "name": r.name,
                "room_type": r.room_type,
                "capacity": r.capacity,
                "price_per_night": str(r.price_per_night),
                "currency": r.currency,
                "total_units": r.total_units,
                "active": r.active,
            })

    menu_items = []
    if company.restaurant_profile and company.restaurant_profile.menu_items:
        menu_items = company.restaurant_profile.menu_items

    leads_count = db.query(func.count(models.PartnerLead.id)).filter(models.PartnerLead.company_id == company.id).scalar() or 0

    return {
        "company": _company_out(company),
        "owner": {
            "id": company.owner.id,
            "full_name": company.owner.full_name,
            "email": company.owner.email,
            "phone": company.owner.phone,
        } if company.owner else None,
        "products": products,
        "services": services,
        "rooms": rooms,
        "menu_items": menu_items,
        "leads_count": leads_count,
    }


# --------------- Create product inside company ---------------

@router.post("/companies/{company_id}/products", status_code=status.HTTP_201_CREATED)
def admin_create_product(
    company_id: int,
    payload: schemmas.ProductIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.producer_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de produtor")

    base_slug = _slugify(payload.name)
    slug = base_slug
    idx = 2
    while db.query(models.ProducerProduct).filter(models.ProducerProduct.slug == slug).first():
        slug = f"{base_slug}-{idx}"
        idx += 1
    product = models.ProducerProduct(
        producer_id=company.producer_profile.id,
        name=payload.name.strip(),
        slug=slug,
        price_label=payload.price_label,
        price_amount=payload.price_amount,
        image_url=payload.image_url,
        category=payload.category,
        short_description=payload.short_description,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "price_label": product.price_label,
        "price_amount": str(product.price_amount) if product.price_amount else None,
        "image_url": product.image_url,
        "category": product.category,
        "short_description": product.short_description,
    }


# --------------- Create service inside company ---------------

@router.post("/companies/{company_id}/services", status_code=status.HTTP_201_CREATED)
def admin_create_service(
    company_id: int,
    payload: schemmas.ServiceIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")

    service = models.CompanyService(
        company_id=company.id,
        name=payload.name.strip(),
        price_label=payload.price_label,
        price_amount=payload.price_amount,
        image_url=payload.image_url,
        category=payload.category,
        short_description=payload.short_description,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return {
        "id": service.id,
        "name": service.name,
        "price_label": service.price_label,
        "price_amount": str(service.price_amount) if service.price_amount else None,
        "image_url": service.image_url,
        "category": service.category,
        "short_description": service.short_description,
    }


# --------------- Password management ---------------

class AdminChangePasswordIn(BaseModel):
    user_id: int
    new_password: str = Field(..., min_length=4, max_length=128)


class AdminResetPasswordIn(BaseModel):
    user_id: int


@router.post("/users/{user_id}/change-password")
def admin_change_password(
    user_id: int,
    payload: AdminChangePasswordIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador nao encontrado")
    user.password_hash = get_password_hash(payload.new_password)
    db.commit()
    return {"detail": "Senha alterada com sucesso"}


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador nao encontrado")
    new_password = _generate_password(8)
    user.password_hash = get_password_hash(new_password)
    db.commit()
    return {"new_password": new_password, "user_id": user.id, "email": user.email}
