from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

import models
import schemmas
from auth import get_current_user
from controllers.notifications import create_notification
from controllers.storage_manager import COMPANIES_FOLDER, storage_manager
from database import get_db


router = APIRouter(prefix="/companies", tags=["companies"])


def _company_type_value(value: schemmas.CompanyCreate | models.CompanyType | str) -> str:
    if isinstance(value, schemmas.CompanyCreate):
        value = value.company_type
    return value.value if hasattr(value, "value") else str(value).strip().lower()


def _company_out(company: models.Company) -> schemmas.CompanyOut:
    return schemmas.CompanyOut(
        id=company.id,
        owner_user_id=company.owner_user_id,
        name=company.name,
        slug=company.slug,
        company_type=company.company_type.value if hasattr(company.company_type, "value") else str(company.company_type),
        category=company.category,
        location=company.location,
        district=company.district,
        description=company.description,
        short_description=company.short_description,
        phone=company.phone,
        email=company.email,
        whatsapp=company.whatsapp,
        website=company.website,
        instagram=company.instagram,
        facebook=company.facebook,
        logo_url=company.logo_url,
        cover_url=company.cover_url,
        status=company.status.value if hasattr(company.status, "value") else str(company.status),
        is_verified=company.is_verified,
        is_featured=company.is_featured,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


def _service_out(item: models.CompanyService) -> schemmas.CompanyServiceOut:
    return schemmas.CompanyServiceOut(
        id=item.id,
        name=item.name,
        price_label=item.price_label,
        price_amount=item.price_amount,
        image=item.image_url,
        category=item.category,
        short_description=item.short_description,
    )


def _product_out(item: models.ProducerProduct) -> schemmas.ProducerProductOut:
    return schemmas.ProducerProductOut(
        id=item.id,
        name=item.name,
        price=item.price_label,
        price_amount=item.price_amount,
        image=item.image_url,
        category=item.category,
        short_description=item.short_description,
    )


def _lead_out(item: models.PartnerLead) -> schemmas.LeadOut:
    return schemmas.LeadOut(
        id=item.id,
        company_id=item.company_id,
        requester_user_id=item.requester_user_id,
        lead_type=item.lead_type.value if hasattr(item.lead_type, "value") else str(item.lead_type),
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        customer_name=item.customer_name,
        customer_email=item.customer_email,
        customer_phone=item.customer_phone,
        message=item.message,
        admin_notes=item.admin_notes,
        check_in_date=item.check_in_date,
        check_out_date=item.check_out_date,
        guests_count=item.guests_count,
        service_name=item.service_name,
        product_name=item.product_name,
        quantity=item.quantity,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _selo_out(item: models.SeloNiassaRequest) -> schemmas.SeloRequestOut:
    return schemmas.SeloRequestOut(
        id=item.id,
        company_id=item.company_id,
        requested_by_user_id=item.requested_by_user_id,
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        motivation=item.motivation,
        documents=list(item.documents or []),
        admin_notes=item.admin_notes,
        reviewed_by_user_id=item.reviewed_by_user_id,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _owned_company(
    db: Session,
    company_id: int,
    current_user: models.User,
) -> models.Company:
    company = (
        db.query(models.Company)
        .options(
            joinedload(models.Company.producer_profile).joinedload(models.ProducerProfile.products),
            joinedload(models.Company.services),
            joinedload(models.Company.leads),
            joinedload(models.Company.selo_requests),
        )
        .filter(models.Company.id == company_id, models.Company.owner_user_id == current_user.id)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    return company


def _is_admin(user: models.User) -> bool:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role == models.UserRole.ADMIN.value


def _slugify(text: str) -> str:
    return "-".join(text.strip().lower().split())


def _ensure_unique_slug(db: Session, slug: str) -> str:
    final_slug = slug
    index = 2
    while db.query(models.Company).filter(models.Company.slug == final_slug).first():
        final_slug = f"{slug}-{index}"
        index += 1
    return final_slug


def _create_company_profile(db: Session, company: models.Company, payload: schemmas.CompanyCreate) -> None:
    company_type = _company_type_value(payload)
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


@router.get("/me", response_model=list[schemmas.CompanyOut])
def list_my_companies(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    companies = (
        db.query(models.Company)
        .options(
            joinedload(models.Company.lodging_profile),
            joinedload(models.Company.experience_profile),
            joinedload(models.Company.restaurant_profile),
            joinedload(models.Company.producer_profile),
        )
        .filter(models.Company.owner_user_id == current_user.id)
        .order_by(models.Company.created_at.desc())
        .all()
    )
    return [_company_out(company) for company in companies]


@router.post("/", response_model=schemmas.CompanyOut)
def create_company_after_login(
    payload: schemmas.CompanyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = models.Company(
        owner_user_id=current_user.id,
        name=payload.name.strip(),
        slug=_ensure_unique_slug(db, _slugify(payload.name)),
        company_type=_company_type_value(payload),
        category=payload.category,
        location=payload.location.strip(),
        district=payload.district,
        description=payload.description,
        short_description=payload.short_description,
        phone=payload.phone.strip(),
        email=payload.email,
        whatsapp=payload.whatsapp,
        website=payload.website,
        instagram=payload.instagram,
        facebook=payload.facebook,
        logo_url=payload.logo_url,
        cover_url=payload.cover_url,
        status=models.CompanyStatus.PENDING,
        is_verified=False,
        is_featured=False,
    )
    db.add(company)
    db.flush()
    _create_company_profile(db, company, payload)
    if (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)) == models.UserRole.CUSTOMER.value:
        current_user.role = models.UserRole.PARTNER
    db.commit()
    db.refresh(company)
    return _company_out(company)


@router.get("/{company_id}", response_model=schemmas.CompanyOut)
def get_my_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = (
        db.query(models.Company)
        .filter(models.Company.id == company_id, models.Company.owner_user_id == current_user.id)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    return _company_out(company)


@router.put("/{company_id}", response_model=schemmas.CompanyOut)
def update_my_company(
    company_id: int,
    payload: schemmas.CompanyUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "status" and not _is_admin(current_user):
            continue
        if key == "is_featured" and not _is_admin(current_user):
            continue
        setattr(company, key, value)
    db.commit()
    db.refresh(company)
    return _company_out(company)


@router.patch("/{company_id}/lodging-profile", response_model=schemmas.CompanyOut)
def update_lodging_profile(
    company_id: int,
    payload: schemmas.LodgingProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.lodging_profile:
        raise HTTPException(status_code=400, detail="Empresa sem perfil de alojamento")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(company.lodging_profile, key, value)
    db.commit()
    db.refresh(company)
    return _company_out(company)


@router.patch("/{company_id}/experience-profile", response_model=schemmas.CompanyOut)
def update_experience_profile(
    company_id: int,
    payload: schemmas.ExperienceProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.experience_profile:
        raise HTTPException(status_code=400, detail="Empresa sem perfil de experiencia")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(company.experience_profile, key, value)
    db.commit()
    db.refresh(company)
    return _company_out(company)


@router.patch("/{company_id}/restaurant-profile", response_model=schemmas.CompanyOut)
def update_restaurant_profile(
    company_id: int,
    payload: schemmas.RestaurantProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.restaurant_profile:
        raise HTTPException(status_code=400, detail="Empresa sem perfil de restaurante")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(company.restaurant_profile, key, value)
    db.commit()
    db.refresh(company)
    return _company_out(company)


@router.patch("/{company_id}/producer-profile", response_model=schemmas.CompanyOut)
def update_producer_profile(
    company_id: int,
    payload: schemmas.ProducerProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.producer_profile:
        raise HTTPException(status_code=400, detail="Empresa sem perfil de produtor/fornecedor")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(company.producer_profile, key, value)
    db.commit()
    db.refresh(company)
    return _company_out(company)


@router.get("/{company_id}/dashboard", response_model=schemmas.SellerDashboardOut)
def get_company_dashboard(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    products = company.producer_profile.products if company.producer_profile else []
    return schemmas.SellerDashboardOut(
        company=_company_out(company),
        products=[_product_out(item) for item in products if item.active],
        services=[_service_out(item) for item in company.services if item.active],
        leads=[_lead_out(item) for item in sorted(company.leads, key=lambda x: x.created_at, reverse=True)],
        selo_requests=[_selo_out(item) for item in sorted(company.selo_requests, key=lambda x: x.created_at, reverse=True)],
    )


@router.post("/{company_id}/upload-logo")
async def upload_company_logo(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    company.logo_url = await storage_manager.upload_file(
        file,
        COMPANIES_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    db.commit()
    return {"url": company.logo_url}


@router.post("/{company_id}/upload-cover")
async def upload_company_cover(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    company.cover_url = await storage_manager.upload_file(
        file,
        COMPANIES_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    db.commit()
    return {"url": company.cover_url}


@router.get("/{company_id}/services", response_model=list[schemmas.CompanyServiceOut])
def list_company_services(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    return [_service_out(item) for item in company.services if item.active]


@router.get("/{company_id}/restaurant-menu", response_model=list[schemmas.RestaurantMenuItem])
def list_restaurant_menu(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.restaurant_profile:
        raise HTTPException(status_code=400, detail="Empresa sem perfil de restaurante")
    return [schemmas.RestaurantMenuItem(**item) for item in (company.restaurant_profile.menu_items or [])]


@router.post("/{company_id}/restaurant-menu", response_model=list[schemmas.RestaurantMenuItem])
def add_restaurant_menu_item(
    company_id: int,
    payload: schemmas.RestaurantMenuItem,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.restaurant_profile:
        raise HTTPException(status_code=400, detail="Empresa sem perfil de restaurante")
    items = list(company.restaurant_profile.menu_items or [])
    items.append(payload.model_dump())
    company.restaurant_profile.menu_items = items
    db.commit()
    return [schemmas.RestaurantMenuItem(**item) for item in items]


@router.delete("/{company_id}/restaurant-menu/{index}", response_model=list[schemmas.RestaurantMenuItem])
def delete_restaurant_menu_item(
    company_id: int,
    index: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.restaurant_profile:
        raise HTTPException(status_code=400, detail="Empresa sem perfil de restaurante")
    items = list(company.restaurant_profile.menu_items or [])
    if index < 0 or index >= len(items):
        raise HTTPException(status_code=404, detail="Item do menu nao encontrado")
    items.pop(index)
    company.restaurant_profile.menu_items = items
    db.commit()
    return [schemmas.RestaurantMenuItem(**item) for item in items]


@router.post("/{company_id}/services", response_model=schemmas.CompanyServiceOut)
def create_company_service(
    company_id: int,
    payload: schemmas.ServiceIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    item = models.CompanyService(
        company_id=company.id,
        name=payload.name.strip(),
        price_label=payload.price_label,
        price_amount=payload.price_amount,
        image_url=payload.image_url,
        category=payload.category,
        short_description=payload.short_description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _service_out(item)


@router.delete("/{company_id}/services/{service_id}")
def delete_company_service(
    company_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    item = next((service for service in company.services if service.id == service_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Servico nao encontrado")
    db.delete(item)
    db.commit()
    return {"status": "ok"}


@router.get("/{company_id}/products", response_model=list[schemmas.ProducerProductOut])
def list_company_products(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.producer_profile:
        return []
    return [_product_out(item) for item in company.producer_profile.products if item.active]


@router.post("/{company_id}/products", response_model=schemmas.ProducerProductOut)
def create_company_product(
    company_id: int,
    payload: schemmas.ProductIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.producer_profile:
        raise HTTPException(status_code=400, detail="Esta empresa nao suporta produtos de mercado")
    item = models.ProducerProduct(
        producer_id=company.producer_profile.id,
        name=payload.name.strip(),
        price_label=payload.price_label,
        price_amount=payload.price_amount,
        image_url=payload.image_url,
        category=payload.category,
        short_description=payload.short_description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _product_out(item)


@router.delete("/{company_id}/products/{product_id}")
def delete_company_product(
    company_id: int,
    product_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    if not company.producer_profile:
        raise HTTPException(status_code=400, detail="Esta empresa nao suporta produtos de mercado")
    item = next((product for product in company.producer_profile.products if product.id == product_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    db.delete(item)
    db.commit()
    return {"status": "ok"}


@router.get("/{company_id}/leads", response_model=list[schemmas.LeadOut])
def list_company_leads(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    return [_lead_out(item) for item in sorted(company.leads, key=lambda x: x.created_at, reverse=True)]


@router.patch("/{company_id}/leads/{lead_id}", response_model=schemmas.LeadOut)
async def update_company_lead(
    company_id: int,
    lead_id: int,
    payload: schemmas.LeadUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    lead = next((item for item in company.leads if item.id == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    lead.status = payload.status
    if payload.admin_notes is not None:
        lead.admin_notes = payload.admin_notes
    db.commit()
    db.refresh(lead)
    if lead.requester_user_id:
        await create_notification(
            db,
            user_id=lead.requester_user_id,
            notification_type=models.NotificationType.LEAD_UPDATED.value,
            title="Pedido atualizado",
            body=f"O estado do seu pedido para {company.name} foi alterado para {lead.status.value if hasattr(lead.status, 'value') else str(lead.status)}.",
            payload={"company_id": company.id, "lead_id": lead.id},
        )
    return _lead_out(lead)


@router.get("/{company_id}/selo", response_model=list[schemmas.SeloRequestOut])
def list_selo_requests(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    return [_selo_out(item) for item in sorted(company.selo_requests, key=lambda x: x.created_at, reverse=True)]


@router.post("/{company_id}/selo", response_model=schemmas.SeloRequestOut)
async def create_selo_request(
    company_id: int,
    payload: schemmas.SeloRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = _owned_company(db, company_id, current_user)
    item = models.SeloNiassaRequest(
        company_id=company.id,
        requested_by_user_id=current_user.id,
        status=models.SeloStatus.PENDING,
        motivation=payload.motivation,
        documents=payload.documents,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    admins = db.query(models.User).filter(models.User.role == models.UserRole.ADMIN.value).all()
    for admin in admins:
        await create_notification(
            db,
            user_id=admin.id,
            notification_type=models.NotificationType.SELO_REQUEST_CREATED.value,
            title="Novo pedido de Selo Niassa",
            body=f"{company.name} solicitou revisão do Selo Niassa.",
            payload={"company_id": company.id, "request_id": item.id},
        )
    return _selo_out(item)


@router.patch("/{company_id}/selo/{request_id}", response_model=schemmas.SeloRequestOut)
async def review_selo_request(
    company_id: int,
    request_id: int,
    payload: schemmas.SeloRequestReview,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas admin pode rever selo")
    item = (
        db.query(models.SeloNiassaRequest)
        .filter(models.SeloNiassaRequest.id == request_id, models.SeloNiassaRequest.company_id == company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Pedido de selo nao encontrado")
    item.status = payload.status
    item.admin_notes = payload.admin_notes
    item.reviewed_by_user_id = current_user.id
    item.reviewed_at = datetime.utcnow()
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if company and payload.status == models.SeloStatus.APPROVED.value:
        company.is_verified = True
    elif company and payload.status == models.SeloStatus.REJECTED.value:
        company.is_verified = False
    db.commit()
    db.refresh(item)
    if company and company.owner_user_id:
        await create_notification(
            db,
            user_id=company.owner_user_id,
            notification_type=models.NotificationType.SELO_REQUEST_REVIEWED.value,
            title="Pedido de Selo atualizado",
            body=f"O pedido de Selo Niassa da empresa {company.name} foi atualizado para {payload.status}.",
            payload={"company_id": company.id, "request_id": item.id, "status": payload.status},
        )
    return _selo_out(item)
