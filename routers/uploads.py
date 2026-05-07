"""
Dedicated upload routes to avoid conflicts.
These are the primary upload endpoints.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from controllers.storage_manager import COMPANIES_FOLDER, storage_manager
from database import get_db


router = APIRouter(prefix="/upload", tags=["uploads"])


def _get_owned_company(db: Session, company_id: int, current_user: models.User) -> models.Company:
    """Get company and ensure user is the owner or admin"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    
    is_owner = company.owner_user_id == current_user.id
    is_admin = current_user.role == models.UserRole.ADMIN or getattr(current_user, "is_admin", False)
    
    if not is_owner and not is_admin:
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta empresa")
    
    return company


@router.post("/company-logo/{company_id}")
async def upload_company_logo(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Upload company logo - NEW DEDICATED ROUTE"""
    company = _get_owned_company(db, company_id, current_user)
    
    url = await storage_manager.upload_file(
        file,
        COMPANIES_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    
    company.logo_url = url
    db.commit()
    db.refresh(company)
    
    return {"url": company.logo_url, "success": True}


@router.post("/company-cover/{company_id}")
async def upload_company_cover(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Upload company cover - NEW DEDICATED ROUTE"""
    company = _get_owned_company(db, company_id, current_user)
    
    url = await storage_manager.upload_file(
        file,
        COMPANIES_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
    
    company.cover_url = url
    db.commit()
    db.refresh(company)
    
    return {"url": company.cover_url, "success": True}
