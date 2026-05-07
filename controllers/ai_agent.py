"""
AI Agent for querying company and product information.
This module provides tools for the AI to access database information.
"""
import json
import re
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

import models


def search_companies(
    db: Session,
    query: str,
    company_type: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Search for companies by name, type, or location.
    """
    q = db.query(models.Company).filter(
        models.Company.status == models.CompanyStatus.APPROVED
    )

    if query:
        q = q.filter(
            or_(
                models.Company.name.ilike(f"%{query}%"),
                models.Company.description.ilike(f"%{query}%"),
                models.Company.location.ilike(f"%{query}%"),
            )
        )

    if company_type:
        q = q.filter(models.Company.company_type == company_type)

    if location:
        q = q.filter(
            or_(
                models.Company.location.ilike(f"%{location}%"),
                models.Company.district.ilike(f"%{location}%"),
            )
        )

    results = q.limit(limit).all()
    return [_company_to_dict(c) for c in results]


def get_company_details(db: Session, company_id: int) -> Optional[dict[str, Any]]:
    """
    Get detailed information about a specific company.
    """
    company = (
        db.query(models.Company)
        .filter(models.Company.id == company_id)
        .filter(models.Company.status == models.CompanyStatus.APPROVED)
        .first()
    )
    if not company:
        return None
    return _company_to_dict(company)


def search_lodgings(
    db: Session, query: str, location: Optional[str] = None, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Search for lodging companies (hotels, apartments, etc).
    """
    q = db.query(models.Company).filter(
        and_(
            models.Company.company_type.in_(
                [
                    models.CompanyType.HOTEL.value,
                    models.CompanyType.LODGING.value,
                    models.CompanyType.HOSPITALITY.value,
                    models.CompanyType.BEACH.value,
                    models.CompanyType.RESTAURANT_RESIDENCE.value,
                ]
            ),
            models.Company.status == models.CompanyStatus.APPROVED,
        )
    )

    if query:
        q = q.filter(
            or_(
                models.Company.name.ilike(f"%{query}%"),
                models.Company.description.ilike(f"%{query}%"),
            )
        )

    if location:
        q = q.filter(
            or_(
                models.Company.location.ilike(f"%{location}%"),
                models.Company.district.ilike(f"%{location}%"),
            )
        )

    results = q.limit(limit).all()
    return [_company_to_dict(c) for c in results]


def search_restaurants(
    db: Session, query: str, location: Optional[str] = None, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Search for restaurant companies.
    """
    q = db.query(models.Company).filter(
        and_(
            models.Company.company_type.in_(
                [
                    models.CompanyType.RESTAURANT.value,
                    models.CompanyType.HOTEL.value,
                ]
            ),
            models.Company.status == models.CompanyStatus.APPROVED,
        )
    )

    if query:
        q = q.filter(
            or_(
                models.Company.name.ilike(f"%{query}%"),
                models.Company.description.ilike(f"%{query}%"),
            )
        )

    if location:
        q = q.filter(
            or_(
                models.Company.location.ilike(f"%{location}%"),
                models.Company.district.ilike(f"%{location}%"),
            )
        )

    results = q.limit(limit).all()
    return [_company_to_dict(c) for c in results]


def search_experiences(
    db: Session, query: str, location: Optional[str] = None, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Search for experience companies (tours, activities, etc).
    """
    q = db.query(models.Company).filter(
        and_(
            models.Company.company_type.in_(
                [
                    models.CompanyType.EXPERIENCE.value,
                    models.CompanyType.TRAVEL_AGENCY.value,
                ]
            ),
            models.Company.status == models.CompanyStatus.APPROVED,
        )
    )

    if query:
        q = q.filter(
            or_(
                models.Company.name.ilike(f"%{query}%"),
                models.Company.description.ilike(f"%{query}%"),
            )
        )

    if location:
        q = q.filter(
            or_(
                models.Company.location.ilike(f"%{location}%"),
                models.Company.district.ilike(f"%{location}%"),
            )
        )

    results = q.limit(limit).all()
    return [_company_to_dict(c) for c in results]


def search_producers(
    db: Session, query: str, location: Optional[str] = None, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Search for producer companies (farms, suppliers, etc).
    """
    q = db.query(models.Company).filter(
        and_(
            models.Company.company_type.in_(
                [
                    models.CompanyType.PRODUCER.value,
                    models.CompanyType.SUPPLIER.value,
                    models.CompanyType.GOODS_SUPPLIER.value,
                    models.CompanyType.AGRO_LIVESTOCK.value,
                ]
            ),
            models.Company.status == models.CompanyStatus.APPROVED,
        )
    )

    if query:
        q = q.filter(
            or_(
                models.Company.name.ilike(f"%{query}%"),
                models.Company.description.ilike(f"%{query}%"),
            )
        )

    if location:
        q = q.filter(
            or_(
                models.Company.location.ilike(f"%{location}%"),
                models.Company.district.ilike(f"%{location}%"),
            )
        )

    results = q.limit(limit).all()
    return [_company_to_dict(c) for c in results]


def search_products(
    db: Session, query: str, category: Optional[str] = None, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Search for products in the market (from producers).
    """
    q = (
        db.query(models.ProducerProduct)
        .join(models.ProducerProfile)
        .join(models.Company)
        .filter(
            models.Company.status == models.CompanyStatus.APPROVED,
            models.ProducerProduct.active == True,
        )
    )

    if query:
        q = q.filter(
            models.ProducerProduct.name.ilike(f"%{query}%")
            | models.ProducerProduct.short_description.ilike(f"%{query}%")
        )

    if category:
        q = q.filter(models.ProducerProduct.category.ilike(f"%{category}%"))

    results = q.limit(limit).all()
    return [_product_to_dict(p) for p in results]


def get_company_stats(db: Session) -> dict[str, Any]:
    """
    Get statistics about companies and products.
    """
    total_companies = (
        db.query(func.count(models.Company.id))
        .filter(models.Company.status == models.CompanyStatus.APPROVED)
        .scalar()
    )

    companies_by_type = (
        db.query(
            models.Company.company_type, func.count(models.Company.id).label("count")
        )
        .filter(models.Company.status == models.CompanyStatus.APPROVED)
        .group_by(models.Company.company_type)
        .all()
    )

    return {
        "total_companies": total_companies,
        "by_type": {
            str(ct).split(".")[-1] if hasattr(ct, "__class__") else ct: count
            for ct, count in companies_by_type
        },
    }


def _company_to_dict(company: models.Company) -> dict[str, Any]:
    """Convert a Company model to a dictionary."""
    return {
        "id": company.id,
        "name": company.name,
        "type": company.company_type.value if hasattr(company.company_type, "value") else str(company.company_type),
        "location": company.location,
        "district": company.district,
        "description": company.short_description or company.description,
        "phone": company.phone,
        "email": company.email,
        "whatsapp": company.whatsapp,
        "website": company.website,
        "instagram": company.instagram,
        "verified": company.is_verified,
        "featured": company.is_featured,
    }


def _product_to_dict(product: models.ProducerProduct) -> dict[str, Any]:
    """Convert a ProducerProduct model to a dictionary."""
    producer_name = None
    try:
        if product.producer and hasattr(product.producer, 'company') and product.producer.company:
            producer_name = product.producer.company.name
    except Exception:
        pass
    
    return {
        "id": product.id,
        "name": product.name,
        "producer_id": product.producer_id,
        "producer_name": producer_name,
        "price": str(product.price_amount) if product.price_amount else product.price_label,
        "category": product.category,
        "description": product.short_description,
        "image": product.image_url,
    }


def extract_search_intent(message: str) -> tuple[str, dict[str, str]]:
    """
    Extract search intent and parameters from a message.
    Returns: (intent_type, parameters)
    
    intent_types: 'companies', 'lodgings', 'restaurants', 'experiences', 'producers', 'products', None
    """
    lower = message.lower()
    
    # Detect intent patterns
    if any(word in lower for word in ["hotel", "alojamento", "hospedagem", "acomodação", "pousada", "hostel", "alojamentos", "hotéis"]):
        intent = "lodgings"
    elif any(word in lower for word in ["restaurante", "comer", "refeição", "comida", "refeicao", "prato", "prato típico", "comidas", "restaurantes", "café", "cafe"]):
        intent = "restaurants"
    elif any(word in lower for word in ["experiência", "tour", "passeio", "atividade", "viagem", "turismo", "tours", "passeios", "atividades", "experiencias"]):
        intent = "experiences"
    elif any(word in lower for word in ["produtor", "agricultor", "fornecedor", "agrícola", "agraria", "produtores", "agricultores", "fornecedores"]):
        intent = "producers"
    elif any(word in lower for word in ["produto", "mercado", "comprar", "venda", "produto", "produtos", "vender", "vende"]):
        intent = "products"
    elif any(word in lower for word in ["empresa", "negócio", "loja", "estabelecimento", "prestador", "empresas", "negócios", "lojas"]):
        intent = "companies"
    else:
        intent = None
    
    # Extract location if mentioned
    location_patterns = [
        r"em (\w+)",
        r"em (\w+ \w+)",
        r"zona (\w+)",
        r"distrito (\w+)",
        r"na (\w+)",
        r"na (\w+ \w+)",
    ]
    location = None
    for pattern in location_patterns:
        match = re.search(pattern, lower)
        if match:
            location = match.group(1).strip()
            break
    
    parameters = {}
    if location:
        parameters["location"] = location
    
    return intent, parameters
