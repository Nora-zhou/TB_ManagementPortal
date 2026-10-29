from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import create_db_and_tables
from routes.products import router as products_router
from routes.orders import router as orders_router
from routes.sub_orders import router as sub_orders_router
from routes.purchase_orders import router as purchase_orders_router
from routes.stats import router as stats_router
from routes.tasks import router as tasks_router
from routes.snapshots import router as snapshots_router
from routes.credentials import router as credentials_router
from routes.rpa_tasks import router as rpa_tasks_router
from routes.profit_analysis import router as profit_router
from rpa.logging_utils import configure_stdout, safe_print

# 桌面启动器拉起进程时 stdout 可能无效，尽早做 UTF-8 适配（失败无感）
configure_stdout()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    try:
        from rpa import runner as _rpa_runner

        _rpa_runner.start_worker()
    except Exception as exc:  # noqa: BLE001 — RPA 依赖缺失不影响主服务
        safe_print(f"[rpa] 工作线程启动失败（不影响主服务）：{exc}")
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
app.include_router(stats_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(snapshots_router, prefix="/api")
app.include_router(credentials_router, prefix="/api")
app.include_router(rpa_tasks_router, prefix="/api")
app.include_router(profit_router, prefix="/api")


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
