from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.paths import APP_DIR

app = FastAPI(title="CFST Controller")
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
