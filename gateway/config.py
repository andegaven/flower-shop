from pydantic import BaseSettings

class Settings(BaseSettings):
    # Microservice endpoints
    AUTH_SERVICE_URL: str = "http://auth_service:8000"
    PRODUCTS_SERVICE_URL: str = "http://product_service:8010"
    ORDERS_SERVICE_URL: str = "http://order_service:8020"
    NOTIFICATIONS_SERVICE_URL: str = "http://notif_service:8030"
    
    # JWT settings (match auth_service's secret)
    JWT_SECRET: str = "gt58s5th5jit7u54id8iu85u7i5e5u9e9tyu5e"
    JWT_ALGORITHM: str = "HS256"

settings = Settings()