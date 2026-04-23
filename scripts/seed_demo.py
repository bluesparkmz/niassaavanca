from auth import get_password_hash
from database import SessionLocal, init_db
from models import (
    Company,
    CompanyStatus,
    CompanyType,
    ExperienceProfile,
    LodgingProfile,
    ProducerProduct,
    ProducerProfile,
    RestaurantProfile,
    User,
    UserRole,
)


def get_or_create_admin(db):
    admin = db.query(User).filter(User.email == "admin@niassa.co.mz").first()
    if admin:
        return admin
    admin = User(
        full_name="Admin Niassa",
        email="admin@niassa.co.mz",
        phone="+258840000000",
        password_hash=get_password_hash("1234"),
        role=UserRole.ADMIN,
    )
    db.add(admin)
    db.flush()
    return admin


def add_lodging(db, owner):
    if db.query(Company).filter(Company.slug == "eco-lodge-lago-niassa").first():
        return
    company = Company(
        owner_user_id=owner.id,
        name="Eco-Lodge Lago Niassa",
        slug="eco-lodge-lago-niassa",
        company_type=CompanyType.LODGING,
        category="Lodge",
        location="Metangula",
        description="Hospede-se em pleno coração do Lago Niassa com vista privilegiada e anfitriões locais.",
        short_description="Lodge com vista direta para o lago.",
        phone="+258841111111",
        status=CompanyStatus.APPROVED,
        is_verified=True,
        is_featured=True,
    )
    db.add(company)
    db.flush()
    db.add(
        LodgingProfile(
            company_id=company.id,
            stay_type="Lodge",
            price_per_night=65,
            currency="EUR",
            rating=4.92,
            badge="Favorito dos hóspedes",
            amenities=["Vista para o lago", "Pequeno-almoço incluído", "Wi-Fi", "Atividades locais"],
        )
    )


def add_experience(db, owner):
    if db.query(Company).filter(Company.slug == "pesca-artesanal-ao-amanhecer").first():
        return
    company = Company(
        owner_user_id=owner.id,
        name="Pesca artesanal ao amanhecer",
        slug="pesca-artesanal-ao-amanhecer",
        company_type=CompanyType.EXPERIENCE,
        category="Pesca",
        location="Metangula",
        description="Vivência em pequeno grupo focada na pesca tradicional e no quotidiano ribeirinho.",
        short_description="Saída cedo com pescadores locais.",
        phone="+258842222222",
        status=CompanyStatus.APPROVED,
        is_featured=True,
    )
    db.add(company)
    db.flush()
    db.add(
        ExperienceProfile(
            company_id=company.id,
            host_name="João Mussa",
            schedule_text="Disponível desde 30 abr.",
            badge="Original Niassa",
            category_label="Pesca",
        )
    )


def add_restaurant(db, owner):
    if db.query(Company).filter(Company.slug == "casa-chambo").first():
        return
    company = Company(
        owner_user_id=owner.id,
        name="Casa Chambo",
        slug="casa-chambo",
        company_type=CompanyType.RESTAURANT,
        category="Peixe do Lago",
        location="Metangula",
        description="Restaurante focado em ingredientes regionais e receitas com identidade local.",
        short_description="Especialidade em peixe fresco do lago.",
        phone="+258843333333",
        status=CompanyStatus.APPROVED,
        is_featured=True,
    )
    db.add(company)
    db.flush()
    db.add(
        RestaurantProfile(
            company_id=company.id,
            cuisine="Peixe do Lago",
            signature="Chambo grelhado em folha de bananeira",
            likes_count=312,
            rating=4.86,
            menu_items=[
                {"name": "Chambo grelhado", "desc": "Peixe fresco do Lago, folha de bananeira, matapa", "price": "MZN 650"},
                {"name": "Camarão piri-piri", "desc": "Marisco do Norte com pão de mandioca", "price": "MZN 850"},
            ],
        )
    )


def add_producer(db, owner):
    if db.query(Company).filter(Company.slug == "cooperativa-tikondane").first():
        return
    company = Company(
        owner_user_id=owner.id,
        name="Cooperativa Tikondane",
        slug="cooperativa-tikondane",
        company_type=CompanyType.PRODUCER,
        category="Artesanato",
        location="Lichinga",
        description="Associação de 32 mulheres bordadeiras que preserva técnicas tradicionais do Niassa há mais de 15 anos.",
        short_description="Artesanato tradicional do Niassa.",
        phone="+258844444444",
        whatsapp="+258844444444",
        status=CompanyStatus.APPROVED,
        is_verified=True,
        is_featured=True,
    )
    db.add(company)
    db.flush()
    producer = ProducerProfile(
        company_id=company.id,
        area="Artesanato",
        rating=4.95,
        sales_count=1240,
        story_quote="Bordamos histórias do Lago em cada cesto.",
        social_links=[
            {"label": "Instagram", "url": "#"},
            {"label": "WhatsApp", "url": "#"},
        ],
    )
    db.add(producer)
    db.flush()
    db.add(
        ProducerProduct(
            producer_id=producer.id,
            name="Cesto bordado tradicional",
            price_label="MZN 850",
            category="Artesanato",
        )
    )
    db.add(
        ProducerProduct(
            producer_id=producer.id,
            name="Capulana pintada à mão",
            price_label="MZN 1.200",
            category="Artesanato",
        )
    )


def main():
    init_db()
    db = SessionLocal()
    try:
        owner = get_or_create_admin(db)
        add_lodging(db, owner)
        add_experience(db, owner)
        add_restaurant(db, owner)
        add_producer(db, owner)
        db.commit()
        print("Seed demo concluído.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
