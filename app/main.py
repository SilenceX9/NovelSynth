import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from app.routes import books, index, dehydrate, qa, settings as settings_router, tasks as tasks_router
from app.storage import Storage
from app.task_manager import init_task_manager

app = FastAPI(title="AI 网文脱水机")

storage = Storage()
app.state.storage = storage


@app.on_event("startup")
async def startup():
    await init_task_manager(storage)


app.include_router(books.router)
app.include_router(index.router)
app.include_router(dehydrate.router)
app.include_router(qa.router)
app.include_router(settings_router.router)
app.include_router(tasks_router.router)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
