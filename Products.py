# Импорт необходимых библиотек
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, status, Query
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError
import logging

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Блок переменных
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://isp_p_Lashkov:12345@77.91.86.135/isp_p_Lashkov"

# Создание объектов FastAPI и SQLAlchemy
app = FastAPI(title="Products Service API", version="1.0.0")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модели базы данных
class Flower(Base):
    __tablename__ = "flowers"
    
    flower_ID = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    color = Column(String(50), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    image_url = Column(String(255))
    is_available = Column(Boolean, default=True)

class Packaging(Base):
    __tablename__ = "packaging"
    
    packaging_ID = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    color = Column(String(50))
    description = Column(Text)
    price = Column(Float, nullable=False)
    image_url = Column(String(255))
    is_available = Column(Boolean, default=True)

class Bouquet(Base):
    __tablename__ = "bouquets"
    
    bouquet_ID = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    base_price = Column(Float, nullable=False)
    description = Column(Text)
    image_url = Column(String(255))
    is_available = Column(Boolean, default=True)
    
    flowers = relationship("BouquetFlower", back_populates="bouquet")

class BouquetFlower(Base):
    __tablename__ = "bouquet_flowers"
    
    bouquet_flower_ID = Column(Integer, primary_key=True, autoincrement=True)
    bouquet_ID = Column(Integer, ForeignKey("bouquets.bouquet_ID"), nullable=False)
    flower_ID = Column(Integer, ForeignKey("flowers.flower_ID"), nullable=False)
    quantity = Column(Integer, nullable=False)
    
    bouquet = relationship("Bouquet", back_populates="flowers")
    flower = relationship("Flower")

# Создание таблиц в базе данных
Base.metadata.create_all(bind=engine)

# Pydantic модели для запросов и ответов
class FlowerBase(BaseModel):
    name: str
    color: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    is_available: bool = True

class FlowerCreate(FlowerBase):
    pass

class FlowerResponse(FlowerBase):
    flower_ID: int
    
    class Config:
        orm_mode = True

class PackagingBase(BaseModel):
    name: str
    color: Optional[str] = None
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    is_available: bool = True

class PackagingResponse(PackagingBase):
    packaging_ID: int
    
    class Config:
        orm_mode = True

class BouquetBase(BaseModel):
    name: str
    base_price: float
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_available: bool = True

class BouquetResponse(BouquetBase):
    bouquet_ID: int
    flowers: List[dict]
    
    class Config:
        orm_mode = True

class CatalogItem(BaseModel):
    id: int
    name: str
    type: str  # "flower", "packaging", "bouquet"
    price: float
    image_url: Optional[str] = None
    description: Optional[str] = None
    is_available: bool
    
    class Config:
        orm_mode = True

# Dependency для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Роуты API
@app.post("/flowers/", response_model=FlowerResponse, status_code=status.HTTP_201_CREATED)
def create_flower(flower: FlowerCreate, db: Session = Depends(get_db)):
    db_flower = Flower(**flower.dict())
    db.add(db_flower)
    try:
        db.commit()
        db.refresh(db_flower)
        return db_flower
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error creating flower: {e}")
        raise HTTPException(status_code=400, detail="Flower creation failed")

@app.get("/flowers/{flower_id}", response_model=FlowerResponse)
def read_flower(flower_id: int, db: Session = Depends(get_db)):
    flower = db.query(Flower).filter(Flower.flower_ID == flower_id).first()
    if flower is None:
        raise HTTPException(status_code=404, detail="Flower not found")
    return flower

@app.get("/flowers/", response_model=List[FlowerResponse])
def read_flowers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    flowers = db.query(Flower).offset(skip).limit(limit).all()
    return flowers

@app.post("/packaging/", response_model=PackagingResponse, status_code=status.HTTP_201_CREATED)
def create_packaging(packaging: PackagingBase, db: Session = Depends(get_db)):
    db_packaging = Packaging(**packaging.dict())
    db.add(db_packaging)
    try:
        db.commit()
        db.refresh(db_packaging)
        return db_packaging
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error creating packaging: {e}")
        raise HTTPException(status_code=400, detail="Packaging creation failed")

@app.get("/packaging/{packaging_id}", response_model=PackagingResponse)
def read_packaging(packaging_id: int, db: Session = Depends(get_db)):
    packaging = db.query(Packaging).filter(Packaging.packaging_ID == packaging_id).first()
    if packaging is None:
        raise HTTPException(status_code=404, detail="Packaging not found")
    return packaging

@app.post("/bouquets/", response_model=BouquetResponse, status_code=status.HTTP_201_CREATED)
def create_bouquet(bouquet: BouquetBase, db: Session = Depends(get_db)):
    db_bouquet = Bouquet(**bouquet.dict())
    db.add(db_bouquet)
    try:
        db.commit()
        db.refresh(db_bouquet)
        return db_bouquet
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error creating bouquet: {e}")
        raise HTTPException(status_code=400, detail="Bouquet creation failed")

@app.get("/bouquets/{bouquet_id}", response_model=BouquetResponse)
def read_bouquet(bouquet_id: int, db: Session = Depends(get_db)):
    bouquet = db.query(Bouquet).filter(Bouquet.bouquet_ID == bouquet_id).first()
    if bouquet is None:
        raise HTTPException(status_code=404, detail="Bouquet not found")
    
    # Получаем состав букета
    flowers = []
    for bf in bouquet.flowers:
        flower = db.query(Flower).filter(Flower.flower_ID == bf.flower_ID).first()
        if flower:
            flowers.append({
                "flower_id": flower.flower_ID,
                "name": flower.name,
                "quantity": bf.quantity,
                "price_per_unit": flower.price
            })
    
    response = BouquetResponse(
        bouquet_ID=bouquet.bouquet_ID,
        name=bouquet.name,
        base_price=bouquet.base_price,
        description=bouquet.description,
        image_url=bouquet.image_url,
        is_available=bouquet.is_available,
        flowers=flowers
    )
    return response

@app.post("/bouquets/{bouquet_id}/flowers/")
def add_flower_to_bouquet(
    bouquet_id: int,
    flower_id: int,
    quantity: int,
    db: Session = Depends(get_db)
):
    # Проверяем существование букета и цветка
    bouquet = db.query(Bouquet).filter(Bouquet.bouquet_ID == bouquet_id).first()
    if not bouquet:
        raise HTTPException(status_code=404, detail="Bouquet not found")
    
    flower = db.query(Flower).filter(Flower.flower_ID == flower_id).first()
    if not flower:
        raise HTTPException(status_code=404, detail="Flower not found")
    
    # Добавляем цветок в букет
    bouquet_flower = BouquetFlower(
        bouquet_ID=bouquet_id,
        flower_ID=flower_id,
        quantity=quantity
    )
    db.add(bouquet_flower)
    try:
        db.commit()
        return {"message": "Flower added to bouquet successfully"}
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error adding flower to bouquet: {e}")
        raise HTTPException(status_code=400, detail="Failed to add flower to bouquet")

@app.get("/search/", response_model=List[CatalogItem])
def search_catalog(
    query: Optional[str] = None,
    category: Optional[str] = Query(None, regex="^(flower|packaging|bouquet)$"),
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: Session = Depends(get_db)
):
    results = []
    
    if category is None or category == "flower":
        flowers_query = db.query(Flower)
        if query:
            flowers_query = flowers_query.filter(Flower.name.ilike(f"%{query}%"))
        if min_price is not None:
            flowers_query = flowers_query.filter(Flower.price >= min_price)
        if max_price is not None:
            flowers_query = flowers_query.filter(Flower.price <= max_price)
        
        flowers = flowers_query.all()
        for flower in flowers:
            results.append(CatalogItem(
                id=flower.flower_ID,
                name=flower.name,
                type="flower",
                price=flower.price,
                image_url=flower.image_url,
                description=flower.description,
                is_available=flower.is_available
            ))
    
    if category is None or category == "packaging":
        packaging_query = db.query(Packaging)
        if query:
            packaging_query = packaging_query.filter(Packaging.name.ilike(f"%{query}%"))
        if min_price is not None:
            packaging_query = packaging_query.filter(Packaging.price >= min_price)
        if max_price is not None:
            packaging_query = packaging_query.filter(Packaging.price <= max_price)
        
        packaging_items = packaging_query.all()
        for item in packaging_items:
            results.append(CatalogItem(
                id=item.packaging_ID,
                name=item.name,
                type="packaging",
                price=item.price,
                image_url=item.image_url,
                description=item.description,
                is_available=item.is_available
            ))
    
    if category is None or category == "bouquet":
        bouquets_query = db.query(Bouquet)
        if query:
            bouquets_query = bouquets_query.filter(Bouquet.name.ilike(f"%{query}%"))
        if min_price is not None:
            bouquets_query = bouquets_query.filter(Bouquet.base_price >= min_price)
        if max_price is not None:
            bouquets_query = bouquets_query.filter(Bouquet.base_price <= max_price)
        
        bouquets = bouquets_query.all()
        for bouquet in bouquets:
            results.append(CatalogItem(
                id=bouquet.bouquet_ID,
                name=bouquet.name,
                type="bouquet",
                price=bouquet.base_price,
                image_url=bouquet.image_url,
                description=bouquet.description,
                is_available=bouquet.is_available
            ))
    
    return results
