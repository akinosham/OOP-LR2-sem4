from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List
import uuid
import json
import os
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


class TodoList(BaseModel):
    id: str
    name: str
    items: List[Item] = []


def load_db():
    if DB_FILE.exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "todolists": {k: TodoList(**v) for k, v in data["todolists"].items()},
                "items": {k: Item(**v) for k, v in data["items"].items()}
            }
    return {"todolists": {}, "items": {}}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        data = {
            "todolists": {k: v.dict() for k, v in db["todolists"].items()},
            "items": {k: v.dict() for k, v in db["items"].items()}
        }
        json.dump(data, f, ensure_ascii=False)


db = load_db()


@app.post("/todolists/")
async def create_todolist(name: str = Form(...)):
    todolist_id = str(uuid.uuid4())
    db["todolists"][todolist_id] = TodoList(id=todolist_id, name=name)
    save_db(db)
    return RedirectResponse(url="/", status_code=303)


@app.post("/todolists/{todolist_id}/delete")
async def delete_todolist(todolist_id: str):
    if todolist_id not in db["todolists"]:
        raise HTTPException(status_code=404, detail="TodoList not found")

    for item in db["todolists"][todolist_id].items:
        del db["items"][item.id]

    del db["todolists"][todolist_id]
    save_db(db)
    return RedirectResponse(url="/", status_code=303)


@app.post("/items/")
async def create_item(todolist_id: str = Form(...), name: str = Form(...), text: str = Form("")):
    item_id = str(uuid.uuid4())
    new_item = Item(id=item_id, name=name, text=text, is_done=False)
    db["items"][item_id] = new_item
    db["todolists"][todolist_id].items.append(new_item)
    save_db(db)
    return RedirectResponse(url=f"/todolists/{todolist_id}/view", status_code=303)


@app.post("/items/{item_id}/toggle")
async def toggle_item(item_id: str):
    if item_id not in db["items"]:
        raise HTTPException(status_code=404, detail="Item not found")

    db["items"][item_id].is_done = not db["items"][item_id].is_done
    save_db(db)

    todolist_id = next(tlid for tlid, tl in db["todolists"].items() if any(item.id == item_id for item in tl.items))
    return RedirectResponse(url=f"/todolists/{todolist_id}/view", status_code=303)


@app.post("/items/{item_id}/delete")
async def delete_item(item_id: str):
    if item_id not in db["items"]:
        raise HTTPException(status_code=404, detail="Item not found")

    todolist_id = None
    for tlid, todolist in db["todolists"].items():
        if any(item.id == item_id for item in todolist.items):
            todolist.items = [item for item in todolist.items if item.id != item_id]
            todolist_id = tlid
            break

    del db["items"][item_id]
    save_db(db)
    return RedirectResponse(url=f"/todolists/{todolist_id}/view", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "todolists": list(db["todolists"].values())})


@app.get("/todolists/{todolist_id}/view", response_class=HTMLResponse)
async def view_todolist(request: Request, todolist_id: str):
    todolist = db["todolists"].get(todolist_id)
    if not todolist:
        raise HTTPException(status_code=404, detail="TodoList not found")
    return templates.TemplateResponse("todolist.html", {"request": request, "todolist": todolist})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)