from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile, Body
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload, defaultload
import logging
import traceback

logger = logging.getLogger(__name__) 

import models
import schemmas
from auth import get_current_user, get_password_hash
from controllers.storage_manager import storage_manager, COMPANIES_FOLDER
from database import get_db
from routers.companies import (
    LODGING_ROOM_BATHROOM_FOLDER,
    RESTAURANT_MENU_FOLDER,
    _company_out,
    _company_type_value,
    _create_company_profile,
    _ensure_company_profiles_for_type,
    _ensure_unique_slug,
    _lodging_room_out,
    _slugify,
)
from sqlalchemy.orm.attributes import flag_modified


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


class AdminCompanyContactsIn(BaseModel):
    phone: str | None = Field(default=None, min_length=5, max_length=30)
    website: str | None = Field(default=None, max_length=255)
    facebook: str | None = Field(default=None, max_length=255)
    instagram: str | None = Field(default=None, max_length=255)


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
        gallery_images=payload.company.gallery_images or [],
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


@router.patch("/companies/{company_id}/contacts", response_model=schemmas.CompanyOut)
def admin_update_company_contacts(
    company_id: int,
    payload: AdminCompanyContactsIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(company, key, value.strip() if isinstance(value, str) and value.strip() else None)

    if not company.phone:
        raise HTTPException(status_code=400, detail="Telefone da empresa e obrigatorio")

    db.commit()
    db.refresh(company)
    return _company_out(company)


@router.delete("/companies/{company_id}")
def admin_delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if company.producer_profile:
        product_ids = [product.id for product in company.producer_profile.products]
        if product_ids:
            db.query(models.Favorite).filter(models.Favorite.product_id.in_(product_ids)).delete(synchronize_session=False)
    db.query(models.Favorite).filter(models.Favorite.company_id == company_id).delete(synchronize_session=False)
    db.delete(company)
    db.commit()
    return {"detail": "Empresa removida com sucesso"}


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


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Nao pode remover a sua propria conta admin")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador nao encontrado")
    db.delete(user)
    db.commit()
    return {"detail": "Utilizador removido com sucesso"}


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
            joinedload(models.Company.producer_profile).selectinload(models.ProducerProfile.products),
            joinedload(models.Company.restaurant_profile),
            joinedload(models.Company.lodging_profile)
            .selectinload(models.LodgingProfile.rooms),
            defaultload(models.Company.lodging_profile)
            .selectinload(models.LodgingProfile.conference_rooms),
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
                "images": r.images or [],
                "short_description": r.short_description,
                "has_private_bathroom": bool(r.has_private_bathroom),
                "bathroom_description": r.bathroom_description,
                "bathroom_images": r.bathroom_images or [],
            })

    conference_rooms = []
    if company.lodging_profile:
        for r in company.lodging_profile.conference_rooms:
            conference_rooms.append({
                "id": r.id,
                "name": r.name,
                "room_type": r.room_type,
                "capacity": r.capacity,
                "price_per_day": str(r.price_per_day),
                "currency": r.currency,
                "total_units": r.total_units,
                "active": r.active,
                "images": r.images or [],
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
        "conference_rooms": conference_rooms,
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


# --------------- List all products ---------------

@router.get("/products")
def admin_list_products(
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    products = db.query(models.ProducerProduct).options(joinedload(models.ProducerProduct.producer)).order_by(models.ProducerProduct.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "price_label": p.price_label,
            "price_amount": str(p.price_amount) if p.price_amount else None,
            "image_url": p.image_url,
            "category": p.category,
            "short_description": p.short_description,
            "company_id": p.producer.company_id,
            "company_name": p.producer.company.name if p.producer.company else None,
            "active": p.active,
            "created_at": p.created_at,
        }
        for p in products
    ]


@router.get("/products/{product_id}")
def admin_get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    product = db.query(models.ProducerProduct).options(joinedload(models.ProducerProduct.producer)).filter(models.ProducerProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "price_label": product.price_label,
        "price_amount": str(product.price_amount) if product.price_amount else None,
        "image_url": product.image_url,
        "category": product.category,
        "short_description": product.short_description,
        "company_id": product.producer.company_id,
        "company_name": product.producer.company.name if product.producer.company else None,
        "active": product.active,
    }


@router.patch("/products/{product_id}")
def admin_update_product(
    product_id: int,
    payload: schemmas.ProductIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    product = db.query(models.ProducerProduct).filter(models.ProducerProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return {"detail": "Produto atualizado"}


@router.post("/products/{product_id}/upload-image")
async def admin_upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    product = db.query(models.ProducerProduct).filter(models.ProducerProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    product.image_url = await storage_manager.upload_file(
        file,
        f"{COMPANIES_FOLDER}/products",
        allowed_mime_prefixes=("image/",),
    )
    db.commit()
    db.refresh(product)
    return {"url": product.image_url}


@router.delete("/products/{product_id}")
def admin_delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    product = db.query(models.ProducerProduct).filter(models.ProducerProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    db.delete(product)
    db.commit()
    return {"detail": "Produto eliminado"}


# --------------- List all services ---------------

@router.get("/services")
def admin_list_services(
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    services = db.query(models.CompanyService).order_by(models.CompanyService.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "price_label": s.price_label,
            "price_amount": str(s.price_amount) if s.price_amount else None,
            "image_url": s.image_url,
            "category": s.category,
            "short_description": s.short_description,
            "company_id": s.company_id,
            "company_name": s.company.name,
            "active": s.active,
            "created_at": s.created_at,
        }
        for s in services
    ]


@router.get("/services/{service_id}")
def admin_get_service(
    service_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    service = db.query(models.CompanyService).filter(models.CompanyService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servico nao encontrado")
    return {
        "id": service.id,
        "name": service.name,
        "price_label": service.price_label,
        "price_amount": str(service.price_amount) if service.price_amount else None,
        "image_url": service.image_url,
        "category": service.category,
        "short_description": service.short_description,
        "company_id": service.company_id,
        "company_name": service.company.name,
        "active": service.active,
    }


@router.patch("/services/{service_id}")
def admin_update_service(
    service_id: int,
    payload: schemmas.ServiceIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    service = db.query(models.CompanyService).filter(models.CompanyService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servico nao encontrado")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(service, key, value)
    db.commit()
    db.refresh(service)
    return {"detail": "Servico atualizado"}


@router.delete("/services/{service_id}")
def admin_delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    service = db.query(models.CompanyService).filter(models.CompanyService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servico nao encontrado")
    db.delete(service)
    db.commit()
    return {"detail": "Servico eliminado"}


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


class AdminPromoteUserIn(BaseModel):
    email: str = Field(..., max_length=140)


@router.post("/users/make-admin")
def admin_make_user_admin(
    payload: AdminPromoteUserIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    email = payload.email.lower().strip()
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador nao encontrado com este email")
    user.role = models.UserRole.ADMIN
    user.is_admin = True
    user.is_active = True
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "is_admin": user.is_admin,
    }


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


# --------------- Image upload endpoints ---------------

@router.post("/upload-logo")
async def admin_upload_logo(
    file: UploadFile = File(...),
    _: models.User = Depends(_require_admin),
):
    """Upload logo for company creation - returns URL to use in create request"""
    url = await storage_manager.upload_file(
        file,
        COMPANIES_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    return {"url": url}


@router.post("/upload-cover")
async def admin_upload_cover(
    file: UploadFile = File(...),
    _: models.User = Depends(_require_admin),
):
    """Upload cover for company creation - returns URL to use in create request"""
    url = await storage_manager.upload_file(
        file,
        COMPANIES_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    return {"url": url}


@router.post("/companies/{company_id}/upload-cover")
async def admin_upload_company_cover(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Upload cover for existing company - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    company.cover_url = await storage_manager.upload_file(
        file,
        COMPANIES_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    db.commit()
    db.refresh(company)
    return {"url": company.cover_url}


@router.post("/companies/{company_id}/upload-logo")
async def admin_upload_company_logo(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Upload logo for existing company - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    company.logo_url = await storage_manager.upload_file(
        file,
        COMPANIES_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    db.commit()
    db.refresh(company)
    return {"url": company.logo_url}


# --------------- Rooms management for admin ---------------

@router.get("/companies/{company_id}/rooms", response_model=list[schemmas.LodgingRoomOut])
def admin_list_rooms(
    company_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """List rooms for a company - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        return []
    return [_lodging_room_out(r) for r in company.lodging_profile.rooms if r.active]


@router.post("/companies/{company_id}/rooms", response_model=schemmas.LodgingRoomOut)
def admin_create_room(
    company_id: int,
    payload: schemmas.LodgingRoomIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Create a room for a company - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de alojamento")
    
    room = models.LodgingRoom(
        lodging_profile_id=company.lodging_profile.id,
        name=payload.name.strip(),
        room_type=payload.room_type,
        capacity=payload.capacity,
        price_per_night=payload.price_per_night,
        currency=payload.currency or "MZN",
        total_units=payload.total_units,
        amenities=payload.amenities,
        images=payload.images,
        short_description=payload.short_description,
        has_private_bathroom=payload.has_private_bathroom,
        bathroom_description=payload.bathroom_description,
        bathroom_images=payload.bathroom_images,
        active=True,
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return _lodging_room_out(room)


@router.patch("/companies/{company_id}/rooms/{room_id}", response_model=schemmas.LodgingRoomOut)
def admin_update_room(
    company_id: int,
    room_id: int,
    payload: schemmas.LodgingRoomUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Update a room for a company - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de alojamento")

    room = next((item for item in company.lodging_profile.rooms if item.id == room_id), None)
    if not room:
        raise HTTPException(status_code=404, detail="Quarto nao encontrado")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    for key, value in data.items():
        setattr(room, key, value)

    db.commit()
    db.refresh(room)
    return _lodging_room_out(room)


@router.delete("/companies/{company_id}/rooms/{room_id}")
def admin_delete_room(
    company_id: int,
    room_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Delete a room - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de alojamento")

    room = next((item for item in company.lodging_profile.rooms if item.id == room_id), None)
    if not room:
        raise HTTPException(status_code=404, detail="Quarto nao encontrado")

    db.delete(room)
    db.commit()
    return {"detail": "Quarto eliminado"}


@router.post("/companies/{company_id}/rooms/{room_id}/upload-image")
async def admin_upload_room_image(
    company_id: int,
    room_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Upload image for a room - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de alojamento")

    room = next((item for item in company.lodging_profile.rooms if item.id == room_id), None)
    if not room:
        raise HTTPException(status_code=404, detail="Quarto nao encontrado")

    if not room.images:
        room.images = []
    image_url = await storage_manager.upload_file(
        file,
        f"{COMPANIES_FOLDER}/lodging/rooms",
        allowed_mime_prefixes=("image/",),
    )
    images = list(room.images or [])
    images.append(image_url)
    room.images = images
    db.commit()
    db.refresh(room)
    return {"url": image_url, "images": list(room.images or [])}


@router.post("/companies/{company_id}/rooms/{room_id}/upload-bathroom-image")
async def admin_upload_room_bathroom_image(
    company_id: int,
    room_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Upload bathroom image for a lodging room - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de alojamento")

    room = next((item for item in company.lodging_profile.rooms if item.id == room_id), None)
    if not room:
        raise HTTPException(status_code=404, detail="Quarto nao encontrado")

    image_url = await storage_manager.upload_file(
        file,
        LODGING_ROOM_BATHROOM_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    bathroom_images = list(room.bathroom_images or [])
    bathroom_images.append(image_url)
    room.bathroom_images = bathroom_images
    db.commit()
    db.refresh(room)
    return {"url": image_url, "bathroom_images": list(room.bathroom_images or [])}


# --------------- Conference Rooms for admin ---------------

@router.get("/companies/{company_id}/conference-rooms", response_model=list[schemmas.ConferenceRoomOut])
def admin_list_conference_rooms(
    company_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """List conference rooms for a company - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        return []
    return [
        schemmas.ConferenceRoomOut(
            id=r.id,
            name=r.name,
            room_type=r.room_type,
            capacity=r.capacity,
            price_per_day=r.price_per_day,
            currency=r.currency,
            total_units=r.total_units,
            amenities=r.amenities or [],
            images=r.images or [],
            short_description=r.short_description,
            active=r.active,
        )
        for r in company.lodging_profile.conference_rooms
    ]


@router.post(
    "/companies/{company_id}/conference-rooms",
    response_model=schemmas.ConferenceRoomOut
)
def admin_create_conference_room(
    company_id: int,
    payload: schemmas.ConferenceRoomIn,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    try:
        company = (
            db.query(models.Company)
            .filter(models.Company.id == company_id)
            .first()
        )

        if not company:
            raise HTTPException(
                status_code=404,
                detail="Empresa nao encontrada"
            )

        if not company.lodging_profile:
            raise HTTPException(
                status_code=400,
                detail="Empresa nao tem perfil de alojamento"
            )

        room = models.ConferenceRoom(
            lodging_profile_id=company.lodging_profile.id,
            name=payload.name.strip(),
            room_type=payload.room_type,
            capacity=payload.capacity,
            price_per_day=payload.price_per_day,
            currency=payload.currency or "MZN",
            total_units=payload.total_units,
            amenities=payload.amenities,
            images=payload.images,
            short_description=payload.short_description,
            active=True,
        )

        db.add(room)
        db.commit()
        db.refresh(room)

        return schemmas.ConferenceRoomOut(
            id=room.id,
            name=room.name,
            room_type=room.room_type,
            capacity=room.capacity,
            price_per_day=room.price_per_day,
            currency=room.currency,
            total_units=room.total_units,
            amenities=room.amenities or [],
            images=room.images or [],
            short_description=room.short_description,
            active=room.active,
        )

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()

        logger.error(
            "Erro ao criar sala de conferencia:\n%s",
            traceback.format_exc()
        )

        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )

@router.delete("/companies/{company_id}/conference-rooms/{room_id}")
def admin_delete_conference_room(
    company_id: int,
    room_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Delete a conference room - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de alojamento")

    room = next((item for item in company.lodging_profile.conference_rooms if item.id == room_id), None)
    if not room:
        raise HTTPException(status_code=404, detail="Sala de conferência nao encontrada")

    db.delete(room)
    db.commit()
    return {"detail": "Sala de conferência eliminada"}


class SmsRequest(BaseModel):
    phone: str
    message: str


@router.post("/send-sms")
def admin_send_sms(
    payload: SmsRequest = Body(...),
    _: models.User = Depends(_require_admin),
):
    """Enviar SMS manualmente - admin only"""
    from controllers.send_sms import send_sms
    result = send_sms(payload.phone, payload.message)
    return result


class BulkSmsRequest(BaseModel):
    phones: list[str]
    message: str


@router.post("/send-bulk-sms")
def admin_send_bulk_sms(
    payload: BulkSmsRequest = Body(...),
    _: models.User = Depends(_require_admin),
):
    """Enviar SMS em massa para marketing - admin only"""
    from controllers.send_sms import send_sms
    results = []
    for phone in payload.phones:
        result = send_sms(phone, payload.message)
        results.append({"phone": phone, "result": result})
    return {"total_sent": len(results), "results": results}


@router.get("/users-with-phone")
def admin_get_users_with_phone(
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Obter lista de usuários cadastrados com telefone - admin only"""
    users = db.query(models.User).filter(models.User.phone.isnot(None)).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "phone": u.phone,
            "role": u.role.value,
        }
        for u in users
    ]


@router.post("/companies/{company_id}/conference-rooms/{room_id}/upload-image")
async def admin_upload_conference_room_image(
    company_id: int,
    room_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Upload image for a conference room - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.lodging_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de alojamento")

    room = next((item for item in company.lodging_profile.conference_rooms if item.id == room_id), None)
    if not room:
        raise HTTPException(status_code=404, detail="Sala de conferência nao encontrada")

    if not room.images:
        room.images = []
    image_url = await storage_manager.upload_file(
        file,
        f"{COMPANIES_FOLDER}/lodging/conference-rooms",
        allowed_mime_prefixes=("image/",),
    )
    room.images.append(image_url)
    db.commit()
    db.refresh(room)
    return {"url": image_url}


# --------------- Menu management for admin ---------------

@router.get("/companies/{company_id}/restaurant-menu", response_model=list[schemmas.RestaurantMenuItem])
def admin_list_menu(
    company_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """List menu items for a company - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.restaurant_profile:
        return []
    return [schemmas.RestaurantMenuItem(**item) for item in (company.restaurant_profile.menu_items or [])]


@router.post("/companies/{company_id}/restaurant-menu", response_model=list[schemmas.RestaurantMenuItem])
def admin_add_menu_item(
    company_id: int,
    payload: schemmas.RestaurantMenuItem,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Add a menu item for a company - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.restaurant_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de restaurante")
    
    items = list(company.restaurant_profile.menu_items or [])
    items.append(payload.model_dump())
    company.restaurant_profile.menu_items = items
    flag_modified(company.restaurant_profile, "menu_items")
    db.commit()
    db.refresh(company)
    return [schemmas.RestaurantMenuItem(**item) for item in items]


@router.put("/companies/{company_id}/restaurant-menu/{index}", response_model=list[schemmas.RestaurantMenuItem])
def admin_update_menu_item(
    company_id: int,
    index: int,
    payload: schemmas.RestaurantMenuItem,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Update a menu item - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.restaurant_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de restaurante")

    items = list(company.restaurant_profile.menu_items or [])
    if index < 0 or index >= len(items):
        raise HTTPException(status_code=404, detail="Item do menu nao encontrado")

    current = dict(items[index])
    updated = {**current, **payload.model_dump()}
    if not payload.image and current.get("image"):
        updated["image"] = current["image"]
    items[index] = updated
    company.restaurant_profile.menu_items = items
    flag_modified(company.restaurant_profile, "menu_items")
    db.commit()
    db.refresh(company)
    return [schemmas.RestaurantMenuItem(**item) for item in items]


@router.delete("/companies/{company_id}/restaurant-menu/{index}", response_model=list[schemmas.RestaurantMenuItem])
def admin_delete_menu_item(
    company_id: int,
    index: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Delete a menu item - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.restaurant_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de restaurante")
    
    items = list(company.restaurant_profile.menu_items or [])
    if index < 0 or index >= len(items):
        raise HTTPException(status_code=404, detail="Item do menu nao encontrado")
    
    items.pop(index)
    company.restaurant_profile.menu_items = items
    flag_modified(company.restaurant_profile, "menu_items")
    db.commit()
    db.refresh(company)
    return [schemmas.RestaurantMenuItem(**item) for item in items]


@router.post("/companies/{company_id}/restaurant-menu/{index}/upload-image")
async def admin_upload_menu_item_image(
    company_id: int,
    index: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(_require_admin),
):
    """Upload image for a menu item - admin only"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not company.restaurant_profile:
        raise HTTPException(status_code=400, detail="Empresa nao tem perfil de restaurante")

    items = list(company.restaurant_profile.menu_items or [])
    if index < 0 or index >= len(items):
        raise HTTPException(status_code=404, detail="Item do menu nao encontrado")

    url = await storage_manager.upload_file(
        file,
        RESTAURANT_MENU_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    items[index]["image"] = url
    company.restaurant_profile.menu_items = items
    flag_modified(company.restaurant_profile, "menu_items")
    db.commit()
    return {"url": url}
