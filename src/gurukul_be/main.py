import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gurukul_be.api.responses import success_response
from gurukul_be.api.v1.auth import router as auth_router
from gurukul_be.core.config import get_settings
from gurukul_be.schemas.common import ApiResponse, HealthData, RootData

logger = logging.getLogger(__name__)

# Create the FastAPI application. Route decorators below attach endpoints to it.
app = FastAPI()


def _status_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Unknown Status Code"


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exception: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body"),
            "message": error["msg"],
            "code": error["type"],
        }
        for error in exception.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "status_code": 422,
            "message": _status_message(422),
            "detail": "Request validation failed",
            "errors": errors,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exception: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exception.status_code,
        headers=exception.headers,
        content={
            "status_code": exception.status_code,
            "message": _status_message(exception.status_code),
            "detail": exception.detail,
            "errors": [],
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(
    request: Request, exception: Exception
) -> JSONResponse:
    logger.exception("Unhandled request error", exc_info=exception)
    return JSONResponse(
        status_code=500,
        content={
            "status_code": 500,
            "message": _status_message(500),
            "detail": "An unexpected error occurred",
            "errors": [],
        },
    )


# Allow the local frontend to call this API from the browser.
# Change this URL if your frontend runs on a different host or port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URLs allowed to call this API.
    allow_credentials=True,  # Allow cookies or other browser credentials.
    allow_methods=["*"],  # Allow GET, POST, PATCH, DELETE, and other HTTP methods.
    allow_headers=[
        "*"
    ],  # Allow request headers such as Authorization and Content-Type.
)

app.include_router(auth_router, prefix=get_settings().API_V1_PREFIX)


@app.get("/health/live", response_model=ApiResponse[HealthData])
def health_live() -> dict[str, object]:
    return success_response({"status": "ok"}, 200)


@app.get("/health/ready", response_model=ApiResponse[HealthData])
def health_ready() -> dict[str, object]:
    return success_response({"status": "ready"}, 200)


@app.get("/", response_model=ApiResponse[RootData])
def root() -> dict[str, object]:
    return success_response({"message": "Gurukul backend is running"}, 200)


def main() -> None:
    # Keep the `gurukul-be` command configured in pyproject.toml working.
    import uvicorn

    uvicorn.run("gurukul_be.main:app", host="127.0.0.1", port=8000, reload=True)
