from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create the FastAPI application. Route decorators below attach endpoints to it.
app = FastAPI()

# Allow the local frontend to call this API from the browser.
# Change this URL if your frontend runs on a different host or port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URLs allowed to call this API.
    allow_credentials=True,  # Allow cookies or other browser credentials.
    allow_methods=["*"],  # Allow GET, POST, PATCH, DELETE, and other HTTP methods.
    allow_headers=["*"],  # Allow request headers such as Authorization and Content-Type.
)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Gurukul backend is running"}


def main() -> None:
    # Keep the `gurukul-be` command configured in pyproject.toml working.
    import uvicorn

    uvicorn.run("gurukul_be.main:app", host="127.0.0.1", port=8000, reload=True)