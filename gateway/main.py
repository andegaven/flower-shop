from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import httpx
from dependencies import get_current_user
from config import settings

app = FastAPI()

# CORS (adjust for frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reverse proxy to microservices
SERVICE_MAP = {
    "/auth": settings.AUTH_SERVICE_URL,
    "/products": settings.PRODUCTS_SERVICE_URL,
    "/orders": settings.ORDERS_SERVICE_URL,
    "/notifications": settings.NOTIFICATIONS_SERVICE_URL,
}

@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def reverse_proxy(
    request: Request, 
    path_name: str,
    user: dict = Depends(get_current_user)  # Auth required for all routes
):
    # Route to the appropriate microservice
    for prefix, url in SERVICE_MAP.items():
        if path_name.startswith(prefix.lstrip("/")):
            target_url = f"{url}/{path_name}"
            break
    else:
        raise HTTPException(status_code=404, detail="Route not found")

    # Forward request
    async with httpx.AsyncClient() as client:
        response = await client.request(
            request.method,
            target_url,
            headers=dict(request.headers),
            params=dict(request.query_params),
            json=await request.json() if request.method in ["POST", "PUT"] else None,
        )
    
    return response.json()

@app.get("/docs", response_class=HTMLResponse)
def all_docs():
    return """
    <h1>Flower Shop API Documentation</h1>
    <ul>
        <li><a href="/auth/docs" target="_blank">Auth Service</a></li>
        <li><a href="/products/docs" target="_blank">Product Service</a></li>
        <li><a href="/orders/docs" target="_blank">Order Service</a></li>
        <li><a href="/notifications/docs" target="_blank">Notification Service</a></li>
    </ul>
    """