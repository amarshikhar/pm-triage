import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .cmms.service import cmms_app  # noqa: E402
from .db import SessionLocal, init_db  # noqa: E402
from .retention import retention_loop  # noqa: E402
from .routes import router, triage_anomaly_async  # noqa: E402
from .seed import seed_if_empty  # noqa: E402
from .simulator import simulator_loop, simulator  # noqa: E402

SIM_INTERVAL_S = float(os.getenv("SIM_INTERVAL_S", "3"))
SIM_ENABLED = os.getenv("SIM_ENABLED", "1") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        if seed_if_empty(db):
            print("[startup] seeded machine catalog + maintenance history")
    finally:
        db.close()

    tasks: list[asyncio.Task] = []
    if SIM_ENABLED:
        tasks.append(asyncio.create_task(simulator_loop(SIM_INTERVAL_S, triage_anomaly_async)))
        print(f"[startup] telemetry simulator running every {SIM_INTERVAL_S}s")
    tasks.append(asyncio.create_task(retention_loop()))
    yield
    simulator.running = False
    for task in tasks:
        task.cancel()


app = FastAPI(title="PM Triage Assistant", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# The maintenance system of record, mounted as a distinct service so it can be
# inspected directly (GET /cmms/api/workorders) exactly as the triage backend
# reaches it — over HTTP, never by importing its internals.
app.mount("/cmms", cmms_app)
