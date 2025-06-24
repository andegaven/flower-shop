import asyncio
import aio_pika
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import aiomysql

# FastAPI приложение
app = FastAPI(
    title="Notification Service",
    version="1.0.0"
)

# Настройки Maildev
SMTP_CONFIG = {
    "host": "77.91.86.135",
    "port": 1025,
    "username": "",
    "password": "",
    "from_email": "notifications@flower-shop.com"
}

# Настройки базы данных
DB_CONFIG = {
    "host": "77.91.86.135",
    "port": 3306,
    "user": "isp_p_Lashkov",
    "password": "12345",
    "db": "isp_p_Lashkov",
}

# Настройки RabbitMQ
RABBITMQ_CONFIG = {
    "host": "77.91.86.135",
    "port": 5672,
    "username": "user1",
    "password": "password1",
    "vhost": "vhost_user1"
}


# Модели данных
class OrderNotification(BaseModel):
    order_id: int
    customer_email: str
    customer_name: str
    order_details: str
    status: str  # "accepted" или "error"
    error_message: Optional[str] = None


class EmailRequest(BaseModel):
    to_email: str
    subject: str
    body: str


# Подключение базы данных
async def create_db_pool():
    return await aiomysql.create_pool(**DB_CONFIG)


# Зависимости
async def get_db_pool():
    db_pool = await create_db_pool()
    try:
        yield db_pool
    finally:
        db_pool.close()
        await db_pool.wait_closed()


# Функции для работы с email
def create_email_message(to_email: str, subject: str, body: str) -> MIMEMultipart:
    message = MIMEMultipart()
    message["From"] = SMTP_CONFIG["from_email"]
    message["To"] = to_email
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))
    return message


async def send_email(email_request: EmailRequest):
    try:
        message = create_email_message(
            to_email=email_request.to_email,
            subject=email_request.subject,
            body=email_request.body
        )

        with smtplib.SMTP(
                host=SMTP_CONFIG["host"],
                port=SMTP_CONFIG["port"]
        ) as server:
            if SMTP_CONFIG["username"] and SMTP_CONFIG["password"]:
                server.login(SMTP_CONFIG["username"], SMTP_CONFIG["password"])
            server.send_message(message)
        return {"status": "Email sent successfully"}
    except Exception as e:
        print(f"Error sending email: {e}")
        return {"error": str(e)}


async def send_order_notification(notification: OrderNotification):
    if notification.status == "accepted":
        subject = f"Заказ #{notification.order_id} принят!"
        body = f"""Уважаемый(ая) {notification.customer_name},

Ваш заказ #{notification.order_id} был успешно принят.

Детали заказа:
{notification.order_details}

Спасибо за покупку в нашем магазине!
"""
    elif notification.status == "error":
        subject = f"Ошибка обработки заказа #{notification.order_id}"
        body = f"""Уважаемый(ая) {notification.customer_name},

При обработке вашего заказа #{notification.order_id} произошла ошибка.

Сообщение об ошибке:
{notification.error_message}

Пожалуйста, свяжитесь с нашей службой поддержки.

Приносим извинения за неудобства.
"""
    else:
        return {"error": "Invalid notification status"}

    email_request = EmailRequest(
        to_email=notification.customer_email,
        subject=subject,
        body=body
    )

    return await send_email(email_request)


# Обработчик сообщений RabbitMQ
async def handle_notification_message(message: aio_pika.abc.AbstractIncomingMessage, db_pool, channel):
    async with message.process():
        try:
            data = json.loads(message.body)
            action = data.get("action")
            response = {"error": "Unknown action"}

            if action == "order_notification":
                notification = OrderNotification(**data)
                response = await send_order_notification(notification)
            elif action == "send_email":
                email_request = EmailRequest(**data)
                response = await send_email(email_request)

            if message.reply_to:
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(response).encode(),
                        correlation_id=message.correlation_id
                    ),
                    routing_key=message.reply_to
                )
        except Exception as e:
            print("Error handling message:", e)


# API Endpoints
@app.post("/send-email/", status_code=status.HTTP_200_OK)
async def api_send_email(email_request: EmailRequest):
    """Отправка произвольного email"""
    result = await send_email(email_request)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "Email sent successfully"}


@app.post("/send-order-notification/", status_code=status.HTTP_200_OK)
async def api_send_order_notification(notification: OrderNotification):
    """Отправка уведомления о статусе заказа"""
    result = await send_order_notification(notification)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "Order notification sent successfully"}


# RabbitMQ Consumer
async def rabbitmq_main(db_pool):
    connection = await aio_pika.connect_robust(
        f"amqp://{RABBITMQ_CONFIG['username']}:{RABBITMQ_CONFIG['password']}@"
        f"{RABBITMQ_CONFIG['host']}:{RABBITMQ_CONFIG['port']}/{RABBITMQ_CONFIG['vhost']}"
    )
    channel = await connection.channel()
    queue = await channel.declare_queue("notification_queue")

    await queue.consume(lambda message: handle_notification_message(message, db_pool, channel))
    print("Notification service (RabbitMQ) is running...")
    await asyncio.Future()


# Запуск приложения
@app.on_event("startup")
async def startup_event():
    db_pool = await create_db_pool()
    await asyncio.create_task(rabbitmq_main(db_pool))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="77.91.86.135", port=8010)
