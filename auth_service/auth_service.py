import asyncio
import aio_pika
import json
import jwt
import aiomysql
import bcrypt
from aio_pika.abc import AbstractIncomingMessage
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext

# FastAPI приложение
app = FastAPI(
    title="Auth Service",
    description="API для аутентификации и регистрации пользователей",
    version="1.0.0"
)

# Настройка JWT и базы данных
JWT_SECRET = "gt58s5th5jit7u54id8iu85u7i5e5u9e9tyu5e"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DB_CONFIG = {
    "host": "77.91.86.135",
    "port": 3306,
    "user": "isp_p_Lashkov",
    "password": "12345",
    "db": "isp_p_Lashkov",
}


# Объекты
class UserCreate(BaseModel):
    username: str
    password: str
    email: str
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# Подключение базы данных
async def create_db_pool():
    return await aiomysql.create_pool(**DB_CONFIG)


# Зависимости
# Зависимость для получения пула соединений
async def get_db_pool():
    db_pool = await create_db_pool()
    try:
        yield db_pool
    finally:
        db_pool.close()
        await db_pool.wait_closed()


# Хэширование пароля
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# Проверка пароля
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# Создание JWT токена
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


# Аутентификация пользователя
async def authenticate_user(username: str, password: str, db_pool):
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = await cur.fetchone()
            if not user or not verify_password(password, user["password"]):
                return None
            return user


# Получение текущего пользователя
async def get_current_user(token: str = Depends(oauth2_scheme), db_pool=Depends(get_db_pool)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("username")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = await cur.fetchone()
            if user is None:
                raise credentials_exception
            return user


# Оригинальные функции для RabbitMQ
async def register_user(data, db_pool):
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    full_name = data.get("full_name")

    if not all([username, password, email]):
        return {"error": "Missing required fields"}

    hashed_pw = hash_password(password)

    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
            if await cur.fetchone():
                return {"error": "Username or email already in use"}
            await cur.execute(
                "INSERT INTO users (username, email, password, full_name) VALUES (%s, %s, %s, %s)",
                (username, email, hashed_pw, full_name)
            )
            await conn.commit()
            user_id = cur.lastrowid
            return {"status": "User registered", "user_id": user_id}


async def login_user(data, db_pool):
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return {"error": "Missing credentials"}

    user = await authenticate_user(username, password, db_pool)
    if not user:
        return {"error": "Invalid credentials"}

    token_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user.get("role", "user")
    }
    access_token = create_access_token(token_payload, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"token": access_token}


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


# API Endpoints
@app.post("/register/", status_code=status.HTTP_201_CREATED)
async def api_register(user: UserCreate, db_pool=Depends(get_db_pool)):
    """Регистрация нового пользователя"""
    result = await register_user(user.dict(), db_pool)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "User registered successfully", "user_id": result.get("user_id")}


@app.post("/token/", response_model=Token)
async def api_login(form_data: OAuth2PasswordRequestForm = Depends(), db_pool=Depends(get_db_pool)):
    """Аутентификация и получение токена"""
    user = await authenticate_user(form_data.username, form_data.password, db_pool)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user.get("role", "user")
    }
    access_token = create_access_token(
        token_payload,
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me/", response_model=UserResponse)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """Получение информации о текущем пользователе"""
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "full_name": current_user.get("full_name")
    }


# RabbitMQ Consumer
async def rabbitmq_main(db_pool):
    connection = await aio_pika.connect_robust("amqp://user1:password1@77.91.86.135:5672/vhost_user1")
    channel = await connection.channel()
    queue = await channel.declare_queue("auth_queue")

    await queue.consume(lambda message: handle_auth_message(message, db_pool, channel))
    print("Auth service (RabbitMQ) is running...")
    await asyncio.Future()


# Запуск приложения
@app.on_event("startup")
async def startup_event():
    db_pool = await create_db_pool()
    await asyncio.create_task(rabbitmq_main(db_pool))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
