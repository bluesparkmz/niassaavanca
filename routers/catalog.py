from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

import models
import schemmas
from auth import get_current_user, get_current_user_optional
from controllers.notifications import create_notification
from database import get_db


router = APIRouter(prefix="/catalog", tags=["catalog"])


def _lodging_summary(profile: models.LodgingProfile) -> schemmas.LodgingSummary:
    company = profile.company
    return schemmas.LodgingSummary(
        id=company.id,
        name=company.name,
        slug=company.slug,
        location=company.location,
        price=profile.price_per_night,
        currency=profile.currency,
        rating=profile.rating,
        image=company.cover_url or company.logo_url,
        badge=profile.badge,
        type=profile.stay_type,
        short_description=company.short_description,
    )


def _experience_summary(profile: models.ExperienceProfile) -> schemmas.ExperienceSummary:
    company = profile.company
    return schemmas.ExperienceSummary(
        id=company.id,
        name=company.name,
        slug=company.slug,
        host=profile.host_name,
        location=company.location,
        date=profile.schedule_text,
        image=company.cover_url or company.logo_url,
        badge=profile.badge,
        category=profile.category_label,
        short_description=company.short_description,
    )


def _restaurant_summary(profile: models.RestaurantProfile) -> schemmas.RestaurantSummary:
    company = profile.company
    return schemmas.RestaurantSummary(
        id=company.id,
        name=company.name,
        slug=company.slug,
        location=company.location,
        rating=profile.rating,
        likes=profile.likes_count,
        image=company.cover_url or company.logo_url,
        cuisine=profile.cuisine,
        signature=profile.signature,
        short_description=company.short_description,
    )


def _producer_summary(profile: models.ProducerProfile) -> schemmas.ProducerSummary:
    company = profile.company
    return schemmas.ProducerSummary(
        id=company.id,
        name=company.name,
        slug=company.slug,
        area=profile.area,
        location=company.location,
        bio=company.description,
        image=company.logo_url,
        cover=company.cover_url or company.logo_url,
        rating=profile.rating,
        sales=profile.sales_count,
        verified=company.is_verified,
        story_quote=profile.story_quote,
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


def _favorite_out(item: models.Favorite) -> schemmas.FavoriteOut:
    return schemmas.FavoriteOut(
        id=item.id,
        target_type=item.target_type.value if hasattr(item.target_type, "value") else str(item.target_type),
        company_id=item.company_id,
        product_id=item.product_id,
        created_at=item.created_at,
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


def _company_summary(company: models.Company) -> schemmas.CompanySummary:
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


@router.get("/home", response_model=schemmas.HomeResponse)
def home(db: Session = Depends(get_db)):
    lodgings = (
        db.query(models.LodgingProfile)
        .join(models.Company)
        .options(joinedload(models.LodgingProfile.company))
        .filter(
            models.LodgingProfile.active == True,
            models.Company.status == models.CompanyStatus.APPROVED,
        )
        .order_by(models.Company.is_featured.desc(), models.LodgingProfile.rating.desc())
        .limit(8)
        .all()
    )
    experiences = (
        db.query(models.ExperienceProfile)
        .join(models.Company)
        .options(joinedload(models.ExperienceProfile.company))
        .filter(
            models.ExperienceProfile.active == True,
            models.Company.status == models.CompanyStatus.APPROVED,
        )
        .order_by(models.Company.is_featured.desc(), models.Company.created_at.desc())
        .limit(6)
        .all()
    )
    restaurants = (
        db.query(models.RestaurantProfile)
        .join(models.Company)
        .options(joinedload(models.RestaurantProfile.company))
        .filter(
            models.RestaurantProfile.active == True,
            models.Company.status == models.CompanyStatus.APPROVED,
        )
        .order_by(models.Company.is_featured.desc(), models.RestaurantProfile.rating.desc())
        .limit(6)
        .all()
    )
    producers = (
        db.query(models.ProducerProfile)
        .join(models.Company)
        .options(joinedload(models.ProducerProfile.company))
        .filter(
            models.ProducerProfile.active == True,
            models.Company.status == models.CompanyStatus.APPROVED,
        )
        .order_by(models.Company.is_featured.desc(), models.Company.is_verified.desc())
        .limit(8)
        .all()
    )
    return schemmas.HomeResponse(
        lodgings=[_lodging_summary(item) for item in lodgings],
        experiences=[_experience_summary(item) for item in experiences],
        restaurants=[_restaurant_summary(item) for item in restaurants],
        producers=[_producer_summary(item) for item in producers],
    )


@router.get("/lodgings", response_model=list[schemmas.LodgingSummary])
def list_lodgings(db: Session = Depends(get_db)):
    items = (
        db.query(models.LodgingProfile)
        .join(models.Company)
        .options(joinedload(models.LodgingProfile.company))
        .filter(models.LodgingProfile.active == True, models.Company.status == models.CompanyStatus.APPROVED)
        .order_by(models.Company.is_featured.desc(), models.LodgingProfile.rating.desc())
        .all()
    )
    return [_lodging_summary(item) for item in items]


@router.get("/lodgings/{slug}", response_model=schemmas.LodgingDetail)
def get_lodging(slug: str, db: Session = Depends(get_db)):
    item = (
        db.query(models.LodgingProfile)
        .join(models.Company)
        .options(joinedload(models.LodgingProfile.company))
        .filter(models.Company.slug == slug, models.Company.status == models.CompanyStatus.APPROVED)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Alojamento nao encontrado")
    summary = _lodging_summary(item)
    services = [_service_out(service) for service in item.company.services if service.active]
    return schemmas.LodgingDetail(
        **summary.model_dump(),
        description=item.company.description,
        amenities=list(item.amenities or []),
        services=services,
    )


@router.get("/experiences", response_model=list[schemmas.ExperienceSummary])
def list_experiences(db: Session = Depends(get_db)):
    items = (
        db.query(models.ExperienceProfile)
        .join(models.Company)
        .options(joinedload(models.ExperienceProfile.company))
        .filter(models.ExperienceProfile.active == True, models.Company.status == models.CompanyStatus.APPROVED)
        .order_by(models.Company.is_featured.desc(), models.Company.created_at.desc())
        .all()
    )
    return [_experience_summary(item) for item in items]


@router.get("/experiences/{slug}", response_model=schemmas.ExperienceDetail)
def get_experience(slug: str, db: Session = Depends(get_db)):
    item = (
        db.query(models.ExperienceProfile)
        .join(models.Company)
        .options(joinedload(models.ExperienceProfile.company))
        .filter(models.Company.slug == slug, models.Company.status == models.CompanyStatus.APPROVED)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Experiencia nao encontrada")
    summary = _experience_summary(item)
    services = [_service_out(service) for service in item.company.services if service.active]
    return schemmas.ExperienceDetail(**summary.model_dump(), description=item.company.description, services=services)


@router.get("/restaurants", response_model=list[schemmas.RestaurantSummary])
def list_restaurants(db: Session = Depends(get_db)):
    items = (
        db.query(models.RestaurantProfile)
        .join(models.Company)
        .options(joinedload(models.RestaurantProfile.company))
        .filter(models.RestaurantProfile.active == True, models.Company.status == models.CompanyStatus.APPROVED)
        .order_by(models.Company.is_featured.desc(), models.RestaurantProfile.rating.desc())
        .all()
    )
    return [_restaurant_summary(item) for item in items]


@router.get("/restaurants/{slug}", response_model=schemmas.RestaurantDetail)
def get_restaurant(slug: str, db: Session = Depends(get_db)):
    item = (
        db.query(models.RestaurantProfile)
        .join(models.Company)
        .options(joinedload(models.RestaurantProfile.company))
        .filter(models.Company.slug == slug, models.Company.status == models.CompanyStatus.APPROVED)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Restaurante nao encontrado")
    summary = _restaurant_summary(item)
    menu = [schemmas.RestaurantMenuItem(**entry) for entry in (item.menu_items or [])]
    services = [_service_out(service) for service in item.company.services if service.active]
    return schemmas.RestaurantDetail(**summary.model_dump(), description=item.company.description, menu=menu, services=services)


@router.get("/producers", response_model=list[schemmas.ProducerSummary])
def list_producers(
    area: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.ProducerProfile)
        .join(models.Company)
        .options(joinedload(models.ProducerProfile.company))
        .filter(models.ProducerProfile.active == True, models.Company.status == models.CompanyStatus.APPROVED)
    )
    if area and area.lower() != "todas":
        query = query.filter(models.ProducerProfile.area.ilike(f"%{area.strip()}%"))
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.Company.name.ilike(term),
                models.Company.location.ilike(term),
                models.Company.description.ilike(term),
            )
        )
    items = query.order_by(models.Company.is_featured.desc(), models.Company.is_verified.desc()).all()
    return [_producer_summary(item) for item in items]


@router.get("/producers/{slug}", response_model=schemmas.ProducerDetail)
def get_producer(slug: str, db: Session = Depends(get_db)):
    item = (
        db.query(models.ProducerProfile)
        .join(models.Company)
        .options(joinedload(models.ProducerProfile.company), joinedload(models.ProducerProfile.products))
        .filter(models.Company.slug == slug, models.Company.status == models.CompanyStatus.APPROVED)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Produtor nao encontrado")
    summary = _producer_summary(item)
    products = [
        schemmas.ProducerProductOut(
            id=product.id,
            name=product.name,
            price=product.price_label,
            price_amount=product.price_amount,
            image=product.image_url,
            category=product.category,
            short_description=product.short_description,
        )
        for product in item.products
        if product.active
    ]
    return schemmas.ProducerDetail(
        **summary.model_dump(),
        phone=item.company.phone,
        email=item.company.email,
        whatsapp=item.company.whatsapp,
        links=list(item.social_links or []),
        products=products,
        services=[_service_out(service) for service in item.company.services if service.active],
    )


@router.get("/market/products", response_model=list[schemmas.MarketProductOut])
def list_market_products(
    area: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.ProducerProduct)
        .join(models.ProducerProfile)
        .join(models.Company)
        .options(joinedload(models.ProducerProduct.producer).joinedload(models.ProducerProfile.company))
        .filter(
            models.ProducerProduct.active == True,
            models.ProducerProfile.active == True,
            models.Company.status == models.CompanyStatus.APPROVED,
        )
    )
    if area and area.lower() != "todas":
        query = query.filter(models.ProducerProfile.area.ilike(f"%{area.strip()}%"))
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.ProducerProduct.name.ilike(term),
                models.Company.name.ilike(term),
                models.Company.location.ilike(term),
                models.Company.description.ilike(term),
            )
        )
    items = query.order_by(models.Company.is_verified.desc(), models.Company.is_featured.desc()).all()
    return [
        schemmas.MarketProductOut(
            id=item.id,
            name=item.name,
            price=item.price_label,
            price_amount=item.price_amount,
            image=item.image_url,
            category=item.category,
            producer=_producer_summary(item.producer),
        )
        for item in items
    ]


@router.get("/favorites", response_model=list[schemmas.FavoriteOut])
def list_my_favorites(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    items = (
        db.query(models.Favorite)
        .filter(models.Favorite.user_id == current_user.id)
        .order_by(models.Favorite.created_at.desc())
        .all()
    )
    return [_favorite_out(item) for item in items]


@router.get("/favorites/collection", response_model=schemmas.FavoriteCollectionOut)
def list_my_favorite_collection(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    items = db.query(models.Favorite).filter(models.Favorite.user_id == current_user.id).all()
    company_ids = [item.company_id for item in items if item.company_id]
    product_ids = [item.product_id for item in items if item.product_id]
    companies = (
        db.query(models.Company)
        .filter(models.Company.id.in_(company_ids))
        .all()
        if company_ids
        else []
    )
    products = (
        db.query(models.ProducerProduct)
        .options(joinedload(models.ProducerProduct.producer).joinedload(models.ProducerProfile.company))
        .filter(models.ProducerProduct.id.in_(product_ids))
        .all()
        if product_ids
        else []
    )
    return schemmas.FavoriteCollectionOut(
        companies=[_company_summary(item) for item in companies],
        products=[
            schemmas.MarketProductOut(
                id=item.id,
                name=item.name,
                price=item.price_label,
                price_amount=item.price_amount,
                image=item.image_url,
                category=item.category,
                producer=_producer_summary(item.producer),
            )
            for item in products
        ],
    )


@router.post("/favorites/toggle", response_model=schemmas.FavoriteOut | dict)
def toggle_favorite(
    payload: schemmas.FavoriteToggleRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    target_type = payload.target_type.strip().lower()
    if target_type not in {models.FavoriteTargetType.COMPANY.value, models.FavoriteTargetType.PRODUCT.value}:
        raise HTTPException(status_code=400, detail="Tipo de favorito invalido")

    query = db.query(models.Favorite).filter(
        models.Favorite.user_id == current_user.id,
        models.Favorite.target_type == target_type,
    )
    if target_type == models.FavoriteTargetType.COMPANY.value:
        if not payload.company_id:
            raise HTTPException(status_code=400, detail="company_id obrigatorio")
        query = query.filter(models.Favorite.company_id == payload.company_id)
    else:
        if not payload.product_id:
            raise HTTPException(status_code=400, detail="product_id obrigatorio")
        query = query.filter(models.Favorite.product_id == payload.product_id)

    existing = query.first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"status": "removed"}

    item = models.Favorite(
        user_id=current_user.id,
        target_type=target_type,
        company_id=payload.company_id,
        product_id=payload.product_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _favorite_out(item)


@router.post("/companies/{company_id}/leads", response_model=schemmas.LeadOut)
async def create_partner_lead(
    company_id: int,
    payload: schemmas.LeadCreate,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_optional),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    lead = models.PartnerLead(
        company_id=company.id,
        requester_user_id=current_user.id if current_user else None,
        lead_type=payload.lead_type,
        status=models.LeadStatus.NEW,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        message=payload.message,
        check_in_date=payload.check_in_date,
        check_out_date=payload.check_out_date,
        guests_count=payload.guests_count,
        service_name=payload.service_name,
        product_name=payload.product_name,
        quantity=payload.quantity,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    owner_id = company.owner_user_id
    if owner_id:
        await create_notification(
            db,
            user_id=owner_id,
            notification_type=models.NotificationType.LEAD_CREATED.value,
            title="Novo pedido recebido",
            body=f"{payload.customer_name} enviou um novo pedido para {company.name}.",
            payload={
                "company_id": company.id,
                "lead_id": lead.id,
                "lead_type": payload.lead_type,
            },
    )
    return _lead_out(lead)


@router.post("/companies/{company_id}/bookings", response_model=schemmas.LeadOut)
async def create_booking_request(
    company_id: int,
    payload: schemmas.LeadCreate,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_optional),
):
    booking_payload = payload.model_copy(update={"lead_type": models.LeadType.BOOKING.value})
    return await create_partner_lead(company_id, booking_payload, db, current_user)


@router.get("/me/bookings", response_model=list[schemmas.LeadOut])
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    items = (
        db.query(models.PartnerLead)
        .filter(models.PartnerLead.requester_user_id == current_user.id)
        .order_by(models.PartnerLead.created_at.desc())
        .all()
    )
    return [_lead_out(item) for item in items]


@router.get("/search", response_model=schemmas.SearchResponse)
def search_catalog(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    term = f"%{q.strip()}%"
    items: list[schemmas.SearchResultItem] = []

    companies = (
        db.query(models.Company)
        .filter(
            models.Company.status == models.CompanyStatus.APPROVED,
            or_(
                models.Company.name.ilike(term),
                models.Company.location.ilike(term),
                models.Company.category.ilike(term),
                models.Company.description.ilike(term),
            ),
        )
        .limit(limit)
        .all()
    )
    for company in companies:
        items.append(
            schemmas.SearchResultItem(
                entity_type=company.company_type.value if hasattr(company.company_type, "value") else str(company.company_type),
                id=company.id,
                slug=company.slug,
                title=company.name,
                subtitle=company.location,
                image=company.cover_url or company.logo_url,
                category=company.category,
            )
        )

    remaining = max(0, limit - len(items))
    if remaining:
        products = (
            db.query(models.ProducerProduct)
            .join(models.ProducerProfile)
            .join(models.Company)
            .filter(
                models.Company.status == models.CompanyStatus.APPROVED,
                or_(
                    models.ProducerProduct.name.ilike(term),
                    models.ProducerProduct.category.ilike(term),
                    models.Company.name.ilike(term),
                ),
            )
            .limit(remaining)
            .all()
        )
        for product in products:
            items.append(
                schemmas.SearchResultItem(
                    entity_type="product",
                    id=product.id,
                    slug=product.producer.company.slug,
                    title=product.name,
                    subtitle=product.producer.company.name,
                    image=product.image_url,
                    category=product.category,
                )
            )

    return schemmas.SearchResponse(query=q, total=len(items), items=items[:limit])


@router.get("/feed/random", response_model=list[schemmas.FeedItemOut])
def random_feed(
    limit: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    companies = (
        db.query(models.Company)
        .filter(models.Company.status == models.CompanyStatus.APPROVED)
        .order_by(func.random())
        .limit(limit)
        .all()
    )
    return [
        schemmas.FeedItemOut(
            entity_type=company.company_type.value if hasattr(company.company_type, "value") else str(company.company_type),
            id=company.id,
            slug=company.slug,
            title=company.name,
            subtitle=company.location,
            image=company.cover_url or company.logo_url,
            category=company.category,
        )
        for company in companies
    ]


@router.get("/categories", response_model=list[schemmas.CategoryGroupOut])
def list_categories(db: Session = Depends(get_db)):
    rows = (
        db.query(models.Company.category, func.count(models.Company.id))
        .filter(models.Company.status == models.CompanyStatus.APPROVED, models.Company.category.isnot(None))
        .group_by(models.Company.category)
        .order_by(func.count(models.Company.id).desc(), models.Company.category.asc())
        .all()
    )
    return [
        schemmas.CategoryGroupOut(
            key=(category or "").strip().lower().replace(" ", "-"),
            label=category,
            count=count,
        )
        for category, count in rows
        if category
    ]
