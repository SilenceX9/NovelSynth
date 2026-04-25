from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import books, index, dehydrate, qa, settings as settings_router

app = FastAPI(title="AI 网文脱水机")

app.include_router(books.router)
app.include_router(index.router)
app.include_router(dehydrate.router)
app.include_router(qa.router)
app.include_router(settings_router.router)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
