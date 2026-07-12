from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR   = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
GLYPH_DIR  = UPLOAD_DIR / "glyphs"
PAGE_DIR   = UPLOAD_DIR / "pages"

# Create dirs on startup
for d in (UPLOAD_DIR, GLYPH_DIR, PAGE_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mojiji")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

MAX_UPLOAD_MB = 20
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}
