from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    status_code: int
    message: str
    data: T


class HealthData(BaseModel):
    status: str


class RootData(BaseModel):
    message: str
