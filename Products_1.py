import pika
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional

# ... (остальные импорты остаются без изменений)

app = FastAPI()

# Глобальные переменные для соединения с RabbitMQ (лучше использовать конфиг)
RABBITMQ_HOST = "localhost"
QUEUE_BOUQUET_UPDATES = "bouquet_updates"
QUEUE_SEARCH_LOGS = "search_logs"

@app.on_event("startup")
def startup_event():
    """Инициализация соединения с RabbitMQ при запуске приложения"""
    app.rabbit_connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST)
    )
    channel = app.rabbit_connection.channel()
    channel.queue_declare(queue=QUEUE_BOUQUET_UPDATES)
    channel.queue_declare(queue=QUEUE_SEARCH_LOGS)
    logger.info("Connected to RabbitMQ")

@app.on_event("shutdown")
def shutdown_event():
    """Закрытие соединения при остановке приложения"""
    if hasattr(app, 'rabbit_connection') and app.rabbit_connection.is_open:
        app.rabbit_connection.close()
        logger.info("RabbitMQ connection closed")

def send_rabbitmq_message(queue: str, message: str):
    """Отправка сообщения в указанную очередь RabbitMQ"""
    try:
        channel = app.rabbit_connection.channel()
        channel.basic_publish(
            exchange='',
            routing_key=queue,
            body=message.encode('utf-8')
        )
        logger.debug(f"Sent to RabbitMQ queue '{queue}': {message}")
    except Exception as e:
        logger.error(f"RabbitMQ error: {str(e)}")

# Модифицированный эндпоинт добавления цветка в букет
@app.post("/bouquet_flowers/")
def add_flower_to_bouquet(
    bouquet_flower: BouquetFlowerCreate,  # Ваша Pydantic-модель
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    db.add(bouquet_flower)
    try:
        db.commit()
        
        # Отправка уведомления в фоне
        background_tasks.add_task(
            send_rabbitmq_message,
            QUEUE_BOUQUET_UPDATES,
            f"Bouquet updated: {bouquet_flower.bouquet_id}"
        )
        
        return {"message": "Flower added to bouquet successfully"}
    
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error adding flower to bouquet: {e}")
        raise HTTPException(status_code=400, detail="Failed to add flower to bouquet")

# Модифицированный эндпоинт поиска
@app.get("/search/", response_model=List[CatalogItem])
def search_catalog(
    query: Optional[str] = None,
    category: Optional[str] = Query(None, regex="^(flower|packaging|bouquet)$"),
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    background_tasks: BackgroundTasks,  # Добавлен фоновый обработчик
    db: Session = Depends(get_db)
):
    # Логирование поискового запроса
    log_entry = {
        "query": query,
        "category": category,
        "min_price": min_price,
        "max_price": max_price,
        "timestamp": datetime.utcnow().isoformat()
    }
    background_tasks.add_task(
        send_rabbitmq_message,
        QUEUE_SEARCH_LOGS,
        json.dumps(log_entry)
    )

    # Оригинальная логика поиска остается без изменений
    results = []
    
    if category is None or category == "flower":
        # ... (flower search logic)
    
    if category is None or category == "packaging":
        # ... (packaging search logic)
    
    if category is None or category == "bouquet":
        # ... (bouquet search logic)
    
    return results
