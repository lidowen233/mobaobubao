from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prisma import Prisma

from app.config import UPLOAD_DIR, ALLOWED_ORIGINS
from app.routers import copybooks, glyphs

# Shared DB instance — routers import from here
db = Prisma()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    # Inject db into routers
    copybooks.db = db
    glyphs.db    = db
    yield
    await db.disconnect()


app = FastAPI(
    title="墨迹 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded images statically
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Routers
app.include_router(copybooks.router, prefix="/api")
app.include_router(glyphs.router,    prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "墨迹 API"}
