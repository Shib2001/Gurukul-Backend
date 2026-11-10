from http import HTTPStatus


def success_response(data: object, status_code: int) -> dict[str, object]:
    return {
        "status_code": status_code,
        "message": HTTPStatus(status_code).phrase,
        "data": data,
    }
