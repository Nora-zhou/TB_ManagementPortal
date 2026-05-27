from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import create_db_and_tables
from routes.products import router as products_router
from routes.orders import router as orders_router
from routes.sub_orders import router as sub_orders_router
from routes.purchase_orders import router as purchase_orders_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="Spec Kit Task Manager",
    description="Lightweight task manager — FastAPI backend, Vue 3 frontend.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(sub_orders_router, prefix="/api")
app.include_router(purchase_orders_router, prefix="/api")


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
