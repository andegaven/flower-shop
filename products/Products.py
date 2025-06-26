import json
import pika
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, status, Query
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError
import logging
import threading
from contextlib import asynccontextmanager

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Блок переменных
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://isp_p_Lashkov:12345@77.91.86.135/isp_p_Lashkov"
RABBITMQ_URL = "amqp://user1:password1@77.91.86.135:5672/vhost_user1"
EXCHANGE_NAME = "flower_shop_events"
QUEUE_NAME = "catalog_events"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code
    yield
    # Shutdown code
    if rabbitmq_channel and rabbitmq_channel.is_open:
        rabbitmq_channel.close()
    logger.info("RabbitMQ connection closed")

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

# Pydantic модели
class FlowerBase(BaseModel):
    name: str
    color: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    is_available: bool = True

class FlowerResponse(FlowerBase):
    flower_ID: int
    
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

class ProductAvailabilityEvent(BaseModel):
    product_id: int
    product_type: str
    is_available: bool

# RabbitMQ подключение и настройка
def setup_rabbitmq():
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    
    # Объявляем обменник
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    
    # Объявляем очередь и привязываем к обменнику
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='product.*')
    
    return channel

# Глобальная переменная для канала RabbitMQ
rabbitmq_channel = setup_rabbitmq()

# Функция для публикации событий
def publish_event(routing_key: str, message: dict):
    try:
        rabbitmq_channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent message
            ))
        logger.info(f"Published event to {routing_key}: {message}")
    except Exception as e:
        logger.error(f"Failed to publish event: {e}")

# Dependency для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Функция для обработки входящих сообщений
def consume_events():
    def callback(ch, method, properties, body):
        try:
            message = json.loads(body)
            logger.info(f"Received event: {message}")
            
            # Здесь можно добавить обработку входящих событий
            # Например, обновление доступности товаров
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    
    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=callback,
        auto_ack=True)
    
    logger.info("Starting RabbitMQ consumer...")
    channel.start_consuming()

# Запускаем потребитель в отдельном потоке
threading.Thread(target=consume_events, daemon=True).start()

# Роуты API
@app.post("/flowers/", response_model=FlowerResponse, status_code=status.HTTP_201_CREATED)
def create_flower(flower: FlowerBase, db: Session = Depends(get_db)):
    db_flower = Flower(**flower.dict())
    db.add(db_flower)
    try:
        db.commit()
        db.refresh(db_flower)
        
        # Публикуем событие о создании нового цветка
        publish_event(
            routing_key='product.flower.created',
            message={
                'flower_id': db_flower.flower_ID,
                'name': db_flower.name,
                'price': db_flower.price,
                'is_available': db_flower.is_available
            }
        )
        
        return db_flower
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error creating flower: {e}")
        raise HTTPException(status_code=400, detail="Flower creation failed")

@app.patch("/flowers/{flower_id}/availability", status_code=status.HTTP_200_OK)
def update_flower_availability(
    flower_id: int,
    availability: ProductAvailabilityEvent,
    db: Session = Depends(get_db)
):
    flower = db.query(Flower).filter(Flower.flower_ID == flower_id).first()
    if flower is None:
        raise HTTPException(status_code=404, detail="Flower not found")
    
    flower.is_available = availability.is_available
    db.commit()
    
    # Публикуем событие об изменении доступности
    publish_event(
        routing_key='product.flower.availability_changed',
        message={
            'product_id': flower_id,
            'product_type': 'flower',
            'is_available': availability.is_available
        }
    )
    
    return {"message": "Flower availability updated successfully"}

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
    
    # Аналогично для packaging и bouquets...
    
    return results

@app.post("/bouquets/{bouquet_id}/flowers/")
def add_flower_to_bouquet(
    bouquet_id: int,
    flower_id: int,
    quantity: int,
    db: Session = Depends(get_db)
):
    bouquet = db.query(Bouquet).filter(Bouquet.bouquet_ID == bouquet_id).first()
    if not bouquet:
        raise HTTPException(status_code=404, detail="Bouquet not found")
    
    flower = db.query(Flower).filter(Flower.flower_ID == flower_id).first()
    if not flower:
        raise HTTPException(status_code=404, detail="Flower not found")
    
    bouquet_flower = BouquetFlower(
        bouquet_ID=bouquet_id,
        flower_ID=flower_id,
        quantity=quantity
    )
    db.add(bouquet_flower)
    try:
        db.commit()
        
        # Публикуем событие об изменении состава букета
        publish_event(
            routing_key='product.bouquet.updated',
            message={
                'bouquet_id': bouquet_id,
                'action': 'flower_added',
                'flower_id': flower_id,
                'quantity': quantity
            }
        )
        
        return {"message": "Flower added to bouquet successfully"}
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error adding flower to bouquet: {e}")
        raise HTTPException(status_code=400, detail="Failed to add flower to bouquet")


