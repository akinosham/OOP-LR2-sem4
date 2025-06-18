from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid
import json
from pathlib import Path

app = FastAPI()

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

DB_FILE = BASE_DIR / "db.json"


class Item(BaseModel):
    id: str
    name: str
    text: str
    is_done: bool
    deleted_at: Optional[datetime] = None


class TodoList(BaseModel):
    id: str
    name: str
    items: List[Item] = []
    deleted_at: Optional[datetime] = None
    total_items: int = 0
    completed_items: int = 0

    @property
    def progress(self) -> float:
        if self.total_items == 0:
            return 0.0
        return round((self.completed_items / self.total_items) * 100, 2)


def load_db():
    if DB_FILE.exists():
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                # Проверяем, не пустой ли файл
                content = f.read().strip()
                if not content:
                    return {"todolists": {}, "items": {}}

                data = json.loads(content)
                return {
                    "todolists": {k: TodoList(**v) for k, v in data.get("todolists", {}).items()},
                    "items": {k: Item(**v) for k, v in data.get("items", {}).items()}
                }
        except json.JSONDecodeError:
            return {"todolists": {}, "items": {}}
    return {"todolists": {}, "items": {}}


def save_db(db):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            data = {
                "todolists": {k: v.dict() for k, v in db["todolists"].items()},
                "items": {k: v.dict() for k, v in db["items"].items()}
            }
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка при сохранении БД: {e}")


db = load_db()


def update_todolist_counts(todolist_id: str):
    todolist = db["todolists"][todolist_id]
    items = [item for item in todolist.items if item.deleted_at is None]
    todolist.total_items = len(items)
    todolist.completed_items = sum(1 for item in items if item.is_done)
    save_db(db)


@app.post("/todolists/")
async def create_todolist(name: str = Form(...)):
    todolist_id = str(uuid.uuid4())
    db["todolists"][todolist_id] = TodoList(id=todolist_id, name=name)
    save_db(db)
    return RedirectResponse(url="/", status_code=303)


@app.post("/todolists/{todolist_id}/delete")
async def soft_delete_todolist(todolist_id: str):
    if todolist_id not in db["todolists"] or db["todolists"][todolist_id].deleted_at:
        raise HTTPException(status_code=404, detail="TodoList not found")

    db["todolists"][todolist_id].deleted_at = datetime.now()
    save_db(db)
    return RedirectResponse(url="/", status_code=303)


@app.post("/items/")
async def create_item(todolist_id: str = Form(...), name: str = Form(...), text: str = Form("")):
    if todolist_id not in db["todolists"] or db["todolists"][todolist_id].deleted_at:
        raise HTTPException(status_code=404, detail="TodoList not found")

    item_id = str(uuid.uuid4())
    new_item = Item(id=item_id, name=name, text=text, is_done=False)
    db["items"][item_id] = new_item
    db["todolists"][todolist_id].items.append(new_item)
    update_todolist_counts(todolist_id)
    return RedirectResponse(url=f"/todolists/{todolist_id}/view", status_code=303)


@app.post("/items/{item_id}/toggle")
async def toggle_item(item_id: str):
    if item_id not in db["items"] or db["items"][item_id].deleted_at:
        raise HTTPException(status_code=404, detail="Item not found")

    item = db["items"][item_id]
    item.is_done = not item.is_done

    todolist_id = next(
        tlid for tlid, tl in db["todolists"].items()
        if not tl.deleted_at and any(i.id == item_id for i in tl.items)
    )
    update_todolist_counts(todolist_id)
    return RedirectResponse(url=f"/todolists/{todolist_id}/view", status_code=303)


@app.post("/items/{item_id}/delete")
async def soft_delete_item(item_id: str):
    if item_id not in db["items"] or db["items"][item_id].deleted_at:
        raise HTTPException(status_code=404, detail="Item not found")

    db["items"][item_id].deleted_at = datetime.now()

    todolist_id = next(
        tlid for tlid, tl in db["todolists"].items()
        if not tl.deleted_at and any(i.id == item_id for i in tl.items)
    )
    update_todolist_counts(todolist_id)
    return RedirectResponse(url=f"/todolists/{todolist_id}/view", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    active_todolists = [tl for tl in db["todolists"].values() if not tl.deleted_at]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "todolists": active_todolists}
    )


@app.get("/todolists/{todolist_id}/view", response_class=HTMLResponse)
async def view_todolist(request: Request, todolist_id: str):
    todolist = db["todolists"].get(todolist_id)
    if not todolist or todolist.deleted_at:
        raise HTTPException(status_code=404, detail="TodoList not found")

    active_items = [item for item in todolist.items if not item.deleted_at]
    todolist.items = active_items

    return templates.TemplateResponse(
        "todolist.html",
        {
            "request": request,
            "todolist": todolist,
            "progress": todolist.progress
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)