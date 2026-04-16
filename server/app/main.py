from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, categories, sessions, notes, ws

app = FastAPI(title="MyTimeLogger API", version="1.0.0")

# Configure CORS
origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(sessions.router)
app.include_router(notes.router)
app.include_router(ws.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to MyTimeLogger API"}
