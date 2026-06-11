from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from urllib.parse import quote_plus

import models
import schemmas
from auth import get_current_user, get_current_user_optional
from controllers.notifications import create_notification
from controllers.send_sms import send_sms
from database import get_db


router = APIRouter(prefix="/catalog", tags=["catalog"])


def _build_whatsapp_order_link(company: models.Company, product_name: str) -> str | None:
    whatsapp = (company.whatsapp or "").strip()
    if not whatsapp:
        return None
    digits = "".join(ch for ch in whatsapp if ch.isdigit())
    if not digits:
        return None
    message = quote_plus(f"Olá, quero pedir o produto: {product_name}")
    return f"https://wa.me/{digits}?text={message}"


def _lodging_summary(profile: models.LodgingProfile) -> schemmas.LodgingSummary:
    company = profile.company
    
    # Get price from first active room if available, otherwise use profile price
    price = profile.price_per_night
    currency = profile.currency
    
    if profile.rooms:
        active_rooms = [room for room in profile.rooms if room.active]
        if active_rooms:
            price = active_rooms[0].price_per_night
            currency = active_rooms[0].currency
    
    return schemmas.LodgingSummary(
        id=company.id,
        name=company.name,
        slug=company.slug,
        location=company.location,
        price=price,
        currency=currency,
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
        supports_lodging=company.lodging_profile is not None,
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


def _lodging_room_out(item: models.LodgingRoom) -> schemmas.LodgingRoomOut:
    return schemmas.LodgingRoomOut(
        id=item.id,
        name=item.name,
        room_type=item.room_type,
        capacity=item.capacity,
        price_per_night=item.price_per_night,
        currency=item.currency,
        total_units=item.total_units,
        amenities=list(item.amenities or []),
        images=list(item.images or []),
        short_description=item.short_description,
        has_private_bathroom=bool(item.has_private_bathroom),
        bathroom_description=item.bathroom_description,
        bathroom_images=list(item.bathroom_images or []),
        active=item.active,
    )


def _conference_room_out(item: models.ConferenceRoom) -> schemmas.ConferenceRoomOut:
    return schemmas.ConferenceRoomOut(
        id=item.id,
        name=item.name,
        room_type=item.room_type,
        capacity=item.capacity,
        price_per_day=item.price_per_day,
        currency=item.currency,
        total_units=item.total_units,
        amenities=list(item.amenities or []),
        images=list(item.images or []),
        short_description=item.short_description,
        active=item.active,
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
        logo_url=company.logo_url,
        cover_url=company.cover_url,
        gallery_images=list(company.gallery_images or []),
        created_at=company.created_at,
    )


def _comment_out(item: models.CompanyComment) -> schemmas.CompanyCommentOut:
    return schemmas.CompanyCommentOut(
        id=item.id,
        company_id=item.company_id,
        user_id=item.user_id,
        user_name=item.user.full_name,
        user_avatar_url=item.user.avatar_url,
        content=item.content,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _company_social_state(
    db: Session,
    company_id: int,
    current_user: models.User | None = None,
) -> schemmas.CompanySocialState:
    likes_count = db.query(models.CompanyLike).filter(models.CompanyLike.company_id == company_id).count()
    followers_count = db.query(models.CompanyFollow).filter(models.CompanyFollow.company_id == company_id).count()
    comments_count = (
        db.query(models.CompanyComment)
        .filter(models.CompanyComment.company_id == company_id, models.CompanyComment.is_visible == True)
        .count()
    )
    liked_by_me = False
    following_by_me = False
    if current_user:
        liked_by_me = (
            db.query(models.CompanyLike)
            .filter(models.CompanyLike.company_id == company_id, models.CompanyLike.user_id == current_user.id)
            .first()
            is not None
        )
        following_by_me = (
            db.query(models.CompanyFollow)
            .filter(models.CompanyFollow.company_id == company_id, models.CompanyFollow.user_id == current_user.id)
            .first()
            is not None
        )
    return schemmas.CompanySocialState(
        company_id=company_id,
        likes_count=likes_count,
        followers_count=followers_count,
        comments_count=comments_count,
        liked_by_me=liked_by_me,
        following_by_me=following_by_me,
    )


def _product_social_state(
    db: Session,
    product_id: int,
    current_user: models.User | None = None,
) -> schemmas.ProductSocialState:
    likes_count = db.query(models.ProductLike).filter(models.ProductLike.product_id == product_id).count()
    liked_by_me = False
    if current_user:
        liked_by_me = (
            db.query(models.ProductLike)
            .filter(models.ProductLike.product_id == product_id, models.ProductLike.user_id == current_user.id)
            .first()
            is not None
        )
    return schemmas.ProductSocialState(
        product_id=product_id,
        likes_count=likes_count,
        liked_by_me=liked_by_me,
    )


@router.get("/home", response_model=schemmas.HomeResponse)
def home(db: Session = Depends(get_db)):
    lodgings = (
        db.query(models.LodgingProfile)
        .join(models.Company)
        .options(joinedload(models.LodgingProfile.company), joinedload(models.LodgingProfile.rooms))
        .filter(
            models.LodgingProfile.active == True,
            # models.Company.status == models.CompanyStatus.APPROVED,
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
            # models.Company.status == models.CompanyStatus.APPROVED,
        )
        .order_by(models.Company.is_featured.desc(), models.Company.created_at.desc())
        .limit(6)
        .all()
    )
    restaurants = (
        db.query(models.RestaurantProfile)
        .join(models.Company)
        .options(joinedload(models.RestaurantProfile.company).joinedload(models.Company.lodging_profile))
        .filter(
            models.RestaurantProfile.active == True,
            # models.Company.status == models.CompanyStatus.APPROVED,
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
            # models.Company.status == models.CompanyStatus.APPROVED,
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
        .options(joinedload(models.LodgingProfile.company), joinedload(models.LodgingProfile.rooms))
        .filter(models.LodgingProfile.active == True)
        .order_by(models.Company.is_featured.desc(), models.LodgingProfile.rating.desc())
        .all()
    )
    return [_lodging_summary(item) for item in items]


@router.get("/lodgings/{slug}", response_model=schemmas.LodgingDetail)
def get_lodging(slug: str, db: Session = Depends(get_db)):
    item = (
        db.query(models.LodgingProfile)
        .join(models.Company)
        .options(
            joinedload(models.LodgingProfile.company),
            joinedload(models.LodgingProfile.company).joinedload(models.Company.restaurant_profile),
            joinedload(models.LodgingProfile.rooms),
            joinedload(models.LodgingProfile.conference_rooms),
        )
        .filter(models.Company.slug == slug)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Alojamento nao encontrado")
    summary = _lodging_summary(item)
    services = [_service_out(service) for service in item.company.services if service.active]
    restaurant_profile = item.company.restaurant_profile
    restaurant_menu = []
    if restaurant_profile and restaurant_profile.active:
        restaurant_menu = [schemmas.RestaurantMenuItem(**entry) for entry in (restaurant_profile.menu_items or [])]
    return schemmas.LodgingDetail(
        **summary.model_dump(),
        description=item.company.description,
        phone=item.company.phone,
        email=item.company.email,
        whatsapp=item.company.whatsapp,
        website=item.company.website,
        amenities=list(item.amenities or []),
        gallery_images=list(item.company.gallery_images or []) + list(item.gallery_images or []),
        beach_access=item.beach_access,
        check_in_time=item.check_in_time,
        check_out_time=item.check_out_time,
        rooms=[_lodging_room_out(room) for room in item.rooms if room.active],
        conference_rooms=[_conference_room_out(room) for room in item.conference_rooms if room.active],
        services=services,
        supports_restaurant=bool(restaurant_profile and restaurant_profile.active),
        restaurant_cuisine=restaurant_profile.cuisine if restaurant_profile and restaurant_profile.active else None,
        restaurant_signature=restaurant_profile.signature if restaurant_profile and restaurant_profile.active else None,
        restaurant_menu=restaurant_menu,
    )


@router.get("/experiences", response_model=list[schemmas.ExperienceSummary])
def list_experiences(db: Session = Depends(get_db)):
    items = (
        db.query(models.ExperienceProfile)
        .join(models.Company)
        .options(joinedload(models.ExperienceProfile.company))
        .filter(models.ExperienceProfile.active == True)
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
        .filter(models.Company.slug == slug)
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
        .options(joinedload(models.RestaurantProfile.company).joinedload(models.Company.lodging_profile))
        .filter(models.RestaurantProfile.active == True)
        .order_by(models.Company.is_featured.desc(), models.RestaurantProfile.rating.desc())
        .all()
    )
    return [_restaurant_summary(item) for item in items]


@router.get("/restaurants/{slug}", response_model=schemmas.RestaurantDetail)
def get_restaurant(slug: str, db: Session = Depends(get_db)):
    item = (
        db.query(models.RestaurantProfile)
        .join(models.Company)
        .options(joinedload(models.RestaurantProfile.company).joinedload(models.Company.lodging_profile))
        .filter(models.Company.slug == slug)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Restaurante nao encontrado")
    summary = _restaurant_summary(item)
    menu = [schemmas.RestaurantMenuItem(**entry) for entry in (item.menu_items or [])]
    services = [_service_out(service) for service in item.company.services if service.active]
    return schemmas.RestaurantDetail(
        **summary.model_dump(),
        description=item.company.description,
        phone=item.company.phone,
        email=item.company.email,
        whatsapp=item.company.whatsapp,
        website=item.company.website,
        gallery_images=list(item.company.gallery_images or []) + list(item.gallery_images or []),
        menu=menu,
        services=services,
    )


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
        .filter(models.ProducerProfile.active == True)
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
        .filter(models.Company.slug == slug)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Produtor nao encontrado")
    summary = _producer_summary(item)
    products = [
        schemmas.ProducerProductOut(
            id=product.id,
            name=product.name,
            slug=product.slug,
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
        website=item.company.website,
        gallery_images=list(item.company.gallery_images or []),
        links=list(item.social_links or []),
        products=products,
        services=[_service_out(service) for service in item.company.services if service.active],
    )


@router.get("/market/products", response_model=list[schemmas.MarketProductOut])
def list_market_products(
    area: str | None = Query(default=None),
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    categoria: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_optional),
):
    query = (
        db.query(models.ProducerProduct)
        .join(models.ProducerProfile)
        .join(models.Company)
        .options(joinedload(models.ProducerProduct.producer).joinedload(models.ProducerProfile.company))
        .filter(
            models.ProducerProduct.active == True,
            models.ProducerProfile.active == True,
            # models.Company.status == models.CompanyStatus.APPROVED,
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
    selected_category = (category or categoria or "").strip()
    if selected_category and selected_category.lower() != "todas":
        query = query.filter(models.ProducerProduct.category.ilike(f"%{selected_category}%"))
    items = query.order_by(models.Company.is_verified.desc(), models.Company.is_featured.desc()).all()
    output: list[schemmas.MarketProductOut] = []
    for item in items:
        social = _product_social_state(db, item.id, current_user)
        output.append(
            schemmas.MarketProductOut(
                id=item.id,
                name=item.name,
                slug=item.slug,
                price=item.price_label,
                price_amount=item.price_amount,
                image=item.image_url,
                category=item.category,
                producer=_producer_summary(item.producer),
                seller_whatsapp=item.producer.company.whatsapp,
                whatsapp_order_link=_build_whatsapp_order_link(item.producer.company, item.name),
                likes_count=social.likes_count,
                liked_by_me=social.liked_by_me,
            )
        )
    return output


@router.get("/market/products/{slug}", response_model=schemmas.MarketProductDetailOut)
def get_market_product(
    slug: str,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_optional),
):
    item = (
        db.query(models.ProducerProduct)
        .join(models.ProducerProfile)
        .join(models.Company)
        .options(joinedload(models.ProducerProduct.producer).joinedload(models.ProducerProfile.company))
        .filter(
            models.ProducerProduct.slug == slug,
            models.ProducerProduct.active == True,
            models.ProducerProfile.active == True,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    social = _product_social_state(db, item.id, current_user)
    return schemmas.MarketProductDetailOut(
        id=item.id,
        name=item.name,
        slug=item.slug,
        price=item.price_label,
        price_amount=item.price_amount,
        image=item.image_url,
        category=item.category,
        producer=_producer_summary(item.producer),
        seller_whatsapp=item.producer.company.whatsapp,
        whatsapp_order_link=_build_whatsapp_order_link(item.producer.company, item.name),
        likes_count=social.likes_count,
        liked_by_me=social.liked_by_me,
        description=item.short_description,
    )


@router.get("/market/categories", response_model=list[schemmas.CategoryGroupOut])
def list_market_categories(db: Session = Depends(get_db)):
    rows = (
        db.query(models.ProducerProduct.category, func.count(models.ProducerProduct.id))
        .join(models.ProducerProfile)
        .join(models.Company)
        .filter(
            models.ProducerProduct.active == True,
            models.ProducerProfile.active == True,
            models.ProducerProduct.category.isnot(None),
        )
        .group_by(models.ProducerProduct.category)
        .order_by(func.count(models.ProducerProduct.id).desc(), models.ProducerProduct.category.asc())
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
                slug=item.slug,
                price=item.price_label,
                price_amount=item.price_amount,
                image=item.image_url,
                category=item.category,
                producer=_producer_summary(item.producer),
                seller_whatsapp=item.producer.company.whatsapp,
                whatsapp_order_link=_build_whatsapp_order_link(item.producer.company, item.name),
                likes_count=_product_social_state(db, item.id, current_user).likes_count,
                liked_by_me=_product_social_state(db, item.id, current_user).liked_by_me,
            )
            for item in products
        ],
    )


@router.get("/products/{product_id}/social", response_model=schemmas.ProductSocialState)
def get_product_social_state(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_optional),
):
    product = db.query(models.ProducerProduct).filter(models.ProducerProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    return _product_social_state(db, product_id, current_user)


@router.post("/products/{product_id}/like", response_model=schemmas.ProductSocialState)
def toggle_product_like(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    product = db.query(models.ProducerProduct).filter(models.ProducerProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    existing = (
        db.query(models.ProductLike)
        .filter(models.ProductLike.product_id == product_id, models.ProductLike.user_id == current_user.id)
        .first()
    )
    if existing:
        db.delete(existing)
    else:
        db.add(models.ProductLike(product_id=product_id, user_id=current_user.id))
    db.commit()
    return _product_social_state(db, product_id, current_user)


@router.get("/companies/{company_id}/social", response_model=schemmas.CompanySocialState)
def get_company_social_state(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_optional),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    return _company_social_state(db, company_id, current_user)


@router.post("/companies/{company_id}/like", response_model=schemmas.CompanySocialState)
def toggle_company_like(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    existing = (
        db.query(models.CompanyLike)
        .filter(models.CompanyLike.company_id == company_id, models.CompanyLike.user_id == current_user.id)
        .first()
    )
    if existing:
        db.delete(existing)
    else:
        db.add(models.CompanyLike(company_id=company_id, user_id=current_user.id))
    db.commit()
    if company.restaurant_profile:
        company.restaurant_profile.likes_count = db.query(models.CompanyLike).filter(models.CompanyLike.company_id == company_id).count()
        db.commit()
    return _company_social_state(db, company_id, current_user)


@router.post("/companies/{company_id}/follow", response_model=schemmas.CompanySocialState)
def toggle_company_follow(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    existing = (
        db.query(models.CompanyFollow)
        .filter(models.CompanyFollow.company_id == company_id, models.CompanyFollow.user_id == current_user.id)
        .first()
    )
    if existing:
        db.delete(existing)
    else:
        db.add(models.CompanyFollow(company_id=company_id, user_id=current_user.id))
    db.commit()
    return _company_social_state(db, company_id, current_user)


@router.get("/companies/{company_id}/comments", response_model=list[schemmas.CompanyCommentOut])
def list_company_comments(company_id: int, db: Session = Depends(get_db)):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    items = (
        db.query(models.CompanyComment)
        .options(joinedload(models.CompanyComment.user))
        .filter(models.CompanyComment.company_id == company_id, models.CompanyComment.is_visible == True)
        .order_by(models.CompanyComment.created_at.desc())
        .all()
    )
    return [_comment_out(item) for item in items]


@router.post("/companies/{company_id}/comments", response_model=schemmas.CompanyCommentOut)
def create_company_comment(
    company_id: int,
    payload: schemmas.CompanyCommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    item = models.CompanyComment(
        company_id=company_id,
        user_id=current_user.id,
        content=payload.content.strip(),
        is_visible=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    item = (
        db.query(models.CompanyComment)
        .options(joinedload(models.CompanyComment.user))
        .filter(models.CompanyComment.id == item.id)
        .first()
    )
    return _comment_out(item)


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
    current_user: models.User = Depends(get_current_user),
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    lead = models.PartnerLead(
        company_id=company.id,
        requester_user_id=current_user.id,
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
    
    # Enviar SMS para o proprietário do produto (empresa)
    phone_to_send = company.whatsapp or company.phone
    
    if phone_to_send:
        # Format phone number - remove non-digits and ensure country code
        digits = "".join(ch for ch in phone_to_send if ch.isdigit())
        
        # If phone has exactly 8 digits, add country code
        if len(digits) == 8:
            digits = "258" + digits
        # If phone doesn't start with country code, add it
        elif not digits.startswith("258"):
            digits = "258" + digits
        
        # Create appropriate message based on lead type
        if payload.lead_type == models.LeadType.BOOKING.value:
            lead_type_label = "reserva"
            message_parts = [
                f"O usuario {current_user.full_name} fez uma nova reserva no Niassa Avanca!",
                f"Empresa: {company.name}"
            ]
            if payload.customer_name:
                message_parts.append(f"Nome: {payload.customer_name}")
            
            if payload.check_in_date and payload.check_out_date:
                message_parts.append(f"Data: {payload.check_in_date} a {payload.check_out_date}")
            if payload.guests_count:
                message_parts.append(f"Hospedes: {payload.guests_count}")
            if payload.customer_phone:
                message_parts.append(f"Contacto: {payload.customer_phone}")
            
            message = ". ".join(message_parts)
        elif payload.lead_type == models.LeadType.CONTACT.value:
            lead_type_label = "contacto"
            # Use the specified SMS template
            contact_phone = current_user.phone or payload.customer_phone
            message = f"Informamos que {current_user.full_name}. Apreciou seu produto no mercado digital NIASSA AVANÇA. Pelo contacto: {contact_phone}, agradeceríamos que lhe retorna-se para ter mais detalhes. Sempre ao seu dispor 24horas por dia"
        else:
            lead_type_label = "pedido"
            message_parts = [
                f"O usuario {current_user.full_name} fez um novo pedido no Niassa Avanca!",
                f"Empresa: {company.name}"
            ]
            if payload.customer_name:
                message_parts.append(f"Nome: {payload.customer_name}")
            
            if payload.product_name:
                message_parts.append(f"Produto: {payload.product_name}")
            if payload.service_name:
                message_parts.append(f"Servico: {payload.service_name}")
            if payload.check_in_date and payload.check_out_date:
                message_parts.append(f"Data: {payload.check_in_date} a {payload.check_out_date}")
            if payload.guests_count:
                message_parts.append(f"Hospedes: {payload.guests_count}")
            if payload.quantity:
                message_parts.append(f"Quantidade: {payload.quantity}")
            if payload.customer_phone:
                message_parts.append(f"Contacto: {payload.customer_phone}")
            if payload.message:
                message_parts.append(f"Mensagem: {payload.message[:100]}")
            
            message = ". ".join(message_parts)
        
        # Send SMS asynchronously (fire and forget)
        try:
            send_sms(digits, message)
        except Exception as e:
            print(f"Erro ao enviar SMS: {e}")
    
    return _lead_out(lead)


@router.post("/companies/{company_id}/bookings", response_model=schemmas.LeadOut)
async def create_booking_request(
    company_id: int,
    payload: schemmas.LeadCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
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
