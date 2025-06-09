import asyncio
import aio_pika
import json
import jwt
import aiomysql
import bcrypt
from aio_pika.abc import AbstractIncomingMessage


# Настройка JWT и базы данных
JWT_SECRET = "gt58s5th5jit7u54id8iu85u7i5e5u9e9tyu5e"
JWT_ALGORITHM = "HS256"

DB_CONFIG = {
    "host": "77.91.86.135",
    "port": 3306,
    "user": "isp_p_Lashkov",
    "password": "12345",
    "db": "isp_p_Lashkov",
}

# Подключение базы данных
async def create_db_pool():
    return await aiomysql.create_pool(**DB_CONFIG)

# Реализация логики регистрации
async def register_user(data, db_pool):
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")

    if not all([username, password, email]):
        return {"error": "Missing required fields"}

    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
            if await cur.fetchone():
                return {"error": "Username or email already in use"}
            await cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, hashed_pw)
            )
            await conn.commit()
            return {"status": "User registered"}
        

# Реализация логики входа
async def login_user(data, db_pool):
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return {"error": "Missing credentials"}

    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = await cur.fetchone()
            if not user:
                return {"error": "User not found"}
            if not bcrypt.checkpw(password.encode(), user["password"].encode()):
                return {"error": "Incorrect password"}

            token_payload = {
                "user_id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user.get("role", "user")
            }
            token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
            return {"token": token}


# Обработчик действий
async def handle_auth_message(message: AbstractIncomingMessage, db_pool, channel):
    async with message.process():
        try:
            data = json.loads(message.body)
            action = data.get("action")
            response = {"error": "Unknown action"}

            if action == "register":
                response = await register_user(data, db_pool)
            elif action == "login":
                response = await login_user(data, db_pool)

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


async def main():
    db_pool = await create_db_pool()
    connection = await aio_pika.connect_robust("amqp://user1:password1@77.91.86.135:5672/vhost_user1")
    channel = await connection.channel()
    queue = await channel.declare_queue("auth_queue")

    await queue.consume(lambda message: handle_auth_message(message, db_pool, channel))
    print("Auth service is running...")
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
