import json
import pika
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Depends, status, Query
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, Text, ForeignKey, TIMESTAMP, Date
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError
import logging
import requests
import threading

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Блок переменных
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://isp_p_Lashkov:12345@77.91.86.135/isp_p_Lashkov"
RABBITMQ_URL = "amqp://user1:password1@77.91.86.135:5672/vhost_user1"
EXCHANGE_NAME = "flower_shop_events"
QUEUE_NAME = "order_events"
PRODUCTS_SERVICE_URL = "http://77.91.86.135:8010"  # URL сервиса заказов

# Создание объектов FastAPI и SQLAlchemy
app = FastAPI(title="Orders Service API", version="1.0.0")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Модели базы данных
class Order(Base):
    __tablename__ = "orders"

    order_ID = Column(Integer, primary_key=True, autoincrement=True)
    user_ID = Column(Integer, nullable=False)
    order_date = Column(TIMESTAMP, default=datetime.now)
    delivery_date = Column(Date, nullable=False)
    delivery_address = Column(Text, nullable=False)
    recipient_name = Column(String(100), nullable=False)
    recipient_phone = Column(String(20), nullable=False)
    message = Column(Text)
    total_price = Column(Float, nullable=False)
    is_payed = Column(Boolean, default=False)

    items = relationship("OrderItem", back_populates="order")
    status_history = relationship("OrderStatusHistory", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    order_item_ID = Column(Integer, primary_key=True, autoincrement=True)
    order_ID = Column(Integer, ForeignKey("orders.order_ID"), nullable=False)
    bouquet_ID = Column(Integer)
    packaging_ID = Column(Integer)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    is_custom = Column(Boolean, default=False)

    order = relationship("Order", back_populates="items")
    custom_bouquet = relationship("CustomBouquet", back_populates="order_item")


class CustomBouquet(Base):
    __tablename__ = "custom_bouquets"

    custom_bouquet_ID = Column(Integer, primary_key=True, autoincrement=True)
    order_item_ID = Column(Integer, ForeignKey("order_items.order_item_ID"), nullable=False)
    flower_ID = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)

    order_item = relationship("OrderItem", back_populates="custom_bouquet")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    history_ID = Column(Integer, primary_key=True, autoincrement=True)
    order_ID = Column(Integer, ForeignKey("orders.order_ID"), nullable=False)
    status = Column(String(50), nullable=False)
    start_date = Column(TIMESTAMP, default=datetime.now)
    end_date = Column(TIMESTAMP)
    comment = Column(Text)

    order = relationship("Order", back_populates="status_history")


# Создание таблиц в базе данных
Base.metadata.create_all(bind=engine)


# Pydantic модели
class OrderItemCreate(BaseModel):
    bouquet_ID: Optional[int] = None
    packaging_ID: Optional[int] = None
    quantity: int
    price: float
    is_custom: bool = False
    custom_flowers: Optional[List[Dict]] = None  # [{"flower_id": 1, "quantity": 5}]


class OrderCreate(BaseModel):
    user_ID: int
    delivery_date: str  # YYYY-MM-DD
    delivery_address: str
    recipient_name: str
    recipient_phone: str
    message: Optional[str] = None
    items: List[OrderItemCreate]


class OrderResponse(BaseModel):
    order_ID: int
    user_ID: int
    order_date: datetime
    delivery_date: str
    delivery_address: str
    recipient_name: str
    recipient_phone: str
    total_price: float
    is_payed: bool
    status: str

    class Config:
        orm_mode = True


class OrderStatusUpdate(BaseModel):
    status: str
    comment: Optional[str] = None


class ProductAvailability(BaseModel):
    id: int
    type: str  # "flower", "bouquet", "packaging"
    available: bool
    name: str
    requested_quantity: int
    available_quantity: int


# RabbitMQ подключение и настройка
def setup_rabbitmq():
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()

    # Объявляем обменник
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

    # Объявляем очередь и привязываем к обменнику
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key='order.*')

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
            routing_key = method.routing_key
            logger.info(f"Received event [{routing_key}]: {message}")

            # Обработка событий от других сервисов
            if routing_key.startswith("product."):
                # Например, обновление информации о товарах
                pass

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()

    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=callback,
        auto_ack=True)

    logger.info("Starting RabbitMQ consumer for orders service...")
    channel.start_consuming()


# Запускаем потребитель в отдельном потоке
threading.Thread(target=consume_events, daemon=True).start()


# Вспомогательные функции
def check_product_availability(product_type: str, product_id: int, quantity: int) -> ProductAvailability:
    """Проверяет доступность товара через сервис каталога"""
    try:
        response = requests.get(f"{PRODUCTS_SERVICE_URL}/products/{product_type}/{product_id}")
        response.raise_for_status()
        product_data = response.json()

        # Для букетов считаем, что доступность определяется флагом is_available
        if product_type == "bouquets":
            return ProductAvailability(
                id=product_id,
                type=product_type,
                available=product_data.get("is_available", False),
                name=product_data.get("name", ""),
                requested_quantity=quantity,
                available_quantity=1 if product_data.get("is_available") else 0
            )

        # Для цветов и упаковки проверяем наличие
        return ProductAvailability(
            id=product_id,
            type=product_type,
            available=product_data.get("is_available", False),
            name=product_data.get("name", ""),
            requested_quantity=quantity,
            available_quantity=999 if product_data.get("is_available") else 0
            # В реальной системе нужно получить реальный остаток
        )

    except requests.RequestException as e:
        logger.error(f"Error checking product availability: {e}")
        return ProductAvailability(
            id=product_id,
            type=product_type,
            available=False,
            name="",
            requested_quantity=quantity,
            available_quantity=0
        )


# Роуты API
@app.post("/orders/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    # Проверка наличия товаров
    unavailable_products = []
    total_price = 0.0

    # Проверяем доступность каждого товара в заказе
    for item in order.items:
        if item.bouquet_ID:
            # Проверка готового букета
            availability = check_product_availability("bouquets", item.bouquet_ID, item.quantity)
            if not availability.available:
                unavailable_products.append({
                    "id": availability.id,
                    "name": availability.name,
                    "type": "bouquet",
                    "requested": availability.requested_quantity,
                    "available": availability.available_quantity
                })
            else:
                total_price += item.price * item.quantity

        elif item.is_custom and item.custom_flowers:
            # Проверка кастомного букета (каждого цветка)
            for flower in item.custom_flowers:
                availability = check_product_availability("flowers", flower["flower_id"], flower["quantity"])
                if not availability.available:
                    unavailable_products.append({
                        "id": availability.id,
                        "name": availability.name,
                        "type": "flower",
                        "requested": availability.requested_quantity,
                        "available": availability.available_quantity
                    })
                else:
                    total_price += flower.get("price", 0) * flower["quantity"]
        else:
            # Упаковка
            if item.packaging_ID:
                availability = check_product_availability("packaging", item.packaging_ID, item.quantity)
                if not availability.available:
                    unavailable_products.append({
                        "id": availability.id,
                        "name": availability.name,
                        "type": "packaging",
                        "requested": availability.requested_quantity,
                        "available": availability.available_quantity
                    })
                else:
                    total_price += item.price * item.quantity

    # Если есть недоступные товары, возвращаем ошибку
    if unavailable_products:
        # Отправляем уведомление о недоступных товарах
        publish_event(
            routing_key="order.items_unavailable",
            message={
                "user_id": order.user_ID,
                "unavailable_products": unavailable_products
            }
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Some products are unavailable",
                "unavailable_products": unavailable_products
            }
        )

    # Создаем заказ
    db_order = Order(
        user_ID=order.user_ID,
        delivery_date=datetime.strptime(order.delivery_date, "%Y-%m-%d").date(),
        delivery_address=order.delivery_address,
        recipient_name=order.recipient_name,
        recipient_phone=order.recipient_phone,
        message=order.message,
        total_price=total_price
    )

    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # Добавляем элементы заказа
    for item in order.items:
        db_item = OrderItem(
            order_ID=db_order.order_ID,
            bouquet_ID=item.bouquet_ID,
            packaging_ID=item.packaging_ID,
            quantity=item.quantity,
            price=item.price,
            is_custom=item.is_custom
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)

        # Если это кастомный букет, добавляем цветы
        if item.is_custom and item.custom_flowers:
            for flower in item.custom_flowers:
                db_custom = CustomBouquet(
                    order_item_ID=db_item.order_item_ID,
                    flower_ID=flower["flower_id"],
                    quantity=flower["quantity"],
                    price=flower.get("price", 0)
                )
                db.add(db_custom)
                db.commit()

    # Добавляем начальный статус заказа
    db_status = OrderStatusHistory(
        order_ID=db_order.order_ID,
        status="created",
        comment="Order created successfully"
    )
    db.add(db_status)
    db.commit()

    # Отправляем уведомление о создании заказа
    publish_event(
        routing_key="order.created",
        message={
            "order_id": db_order.order_ID,
            "user_id": db_order.user_ID,
            "total_price": db_order.total_price,
            "status": "created"
        }
    )

    # Отправляем уведомление об ожидании оплаты
    publish_event(
        routing_key="order.pending_payment",
        message={
            "order_id": db_order.order_ID,
            "user_id": db_order.user_ID,
            "total_price": db_order.total_price
        }
    )

    # Формируем ответ
    return OrderResponse(
        order_ID=db_order.order_ID,
        user_ID=db_order.user_ID,
        order_date=db_order.order_date,
        delivery_date=db_order.delivery_date.strftime("%Y-%m-%d"),
        delivery_address=db_order.delivery_address,
        recipient_name=db_order.recipient_name,
        recipient_phone=db_order.recipient_phone,
        total_price=db_order.total_price,
        is_payed=db_order.is_payed,
        status="created"
    )


@app.put("/orders/{order_id}/status", response_model=OrderResponse)
def update_order_status(
        order_id: int,
        status_update: OrderStatusUpdate,
        db: Session = Depends(get_db)
):
    # Находим заказ
    order = db.query(Order).filter(Order.order_ID == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Закрываем предыдущий статус
    current_status = db.query(OrderStatusHistory).filter(
        OrderStatusHistory.order_ID == order_id,
        OrderStatusHistory.end_date.is_(None)
    ).first()

    if current_status:
        current_status.end_date = datetime.now()
        db.commit()

    # Добавляем новый статус
    new_status = OrderStatusHistory(
        order_ID=order_id,
        status=status_update.status,
        comment=status_update.comment
    )
    db.add(new_status)
    db.commit()

    # Отправляем уведомление об изменении статуса
    publish_event(
        routing_key=f"order.status.{status_update.status.lower()}",
        message={
            "order_id": order_id,
            "user_id": order.user_ID,
            "status": status_update.status,
            "comment": status_update.comment
        }
    )

    # Если статус "оплачен", обновляем заказ
    if status_update.status.lower() == "paid":
        order.is_payed = True
        db.commit()

        publish_event(
            routing_key="order.paid",
            message={
                "order_id": order_id,
                "user_id": order.user_ID,
                "total_price": order.total_price
            }
        )

    # Формируем ответ
    return OrderResponse(
        order_ID=order.order_ID,
        user_ID=order.user_ID,
        order_date=order.order_date,
        delivery_date=order.delivery_date.strftime("%Y-%m-%d"),
        delivery_address=order.delivery_address,
        recipient_name=order.recipient_name,
        recipient_phone=order.recipient_phone,
        total_price=order.total_price,
        is_payed=order.is_payed,
        status=status_update.status
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_ID == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Получаем текущий статус
    current_status = db.query(OrderStatusHistory).filter(
        OrderStatusHistory.order_ID == order_id,
        OrderStatusHistory.end_date.is_(None)
    ).first()

    status_text = current_status.status if current_status else "unknown"

    return OrderResponse(
        order_ID=order.order_ID,
        user_ID=order.user_ID,
        order_date=order.order_date,
        delivery_date=order.delivery_date.strftime("%Y-%m-%d"),
        delivery_address=order.delivery_address,
        recipient_name=order.recipient_name,
        recipient_phone=order.recipient_phone,
        total_price=order.total_price,
        is_payed=order.is_payed,
        status=status_text
    )


@app.get("/users/{user_id}/orders", response_model=List[OrderResponse])
def get_user_orders(user_id: int, db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.user_ID == user_id).all()
    result = []

    for order in orders:
        # Получаем текущий статус для каждого заказа
        current_status = db.query(OrderStatusHistory).filter(
            OrderStatusHistory.order_ID == order.order_ID,
            OrderStatusHistory.end_date.is_(None)
        ).first()

        status_text = current_status.status if current_status else "unknown"

        result.append(OrderResponse(
            order_ID=order.order_ID,
            user_ID=order.user_ID,
            order_date=order.order_date,
            delivery_date=order.delivery_date.strftime("%Y-%m-%d"),
            delivery_address=order.delivery_address,
            recipient_name=order.recipient_name,
            recipient_phone=order.recipient_phone,
            total_price=order.total_price,
            is_payed=order.is_payed,
            status=status_text
        ))

    return result


# Обработчик для graceful shutdown
@app.on_event("shutdown")
def shutdown_event():
    if rabbitmq_channel and rabbitmq_channel.is_open:
        rabbitmq_channel.close()
    logger.info("RabbitMQ connection closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)
