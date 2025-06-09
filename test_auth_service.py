import asyncio
import aio_pika
import json
import uuid

AMQP_URL = "amqp://user1:password1@77.91.86.135:5672/vhost_user1"


async def send_request(payload):
    connection = await aio_pika.connect_robust(AMQP_URL)
    channel = await connection.channel()

    callback_queue = await channel.declare_queue(exclusive=True)
    correlation_id = str(uuid.uuid4())

    future = asyncio.Future()

    async def on_response(message: aio_pika.IncomingMessage):
        if message.correlation_id == correlation_id:
            future.set_result(message.body)

    await callback_queue.consume(on_response)

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            correlation_id=correlation_id,
            reply_to=callback_queue.name
        ),
        routing_key="auth_queue"
    )

    response = await future
    print("Ответ:", json.loads(response))
    await connection.close()

# Пример регистрации
payload_register = {
    "action": "register",
    "username": "test_user",
    "email": "test@example.com",
    "password": "test123"
}

# Пример логина
payload_login = {
    "action": "login",
    "username": "test_user",
    "password": "test123"
}

# Запуск по очереди
asyncio.run(send_request(payload_register))
# asyncio.run(send_request(payload_login))