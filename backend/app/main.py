from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse


from .config import get_settings
from .routers import auth, game
from .database import engine
from .models import Base
from .auth import start_nonce_cleanup, stop_nonce_cleanup

settings = get_settings()
app = FastAPI(title="Game Collectible API")

# Create database tables
Base.metadata.create_all(bind=engine)

# Start nonce cleanup background task
@app.on_event("startup")
async def startup_event():
    start_nonce_cleanup()

#Stop nonce cleanup background task
@app.on_event("shutdown")
async def shutdown_event():
    """Stop background tasks on app shutdown"""
    await stop_nonce_cleanup()


app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(game.router)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return RedirectResponse(url="/docs")