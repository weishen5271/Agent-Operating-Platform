from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException


ERROR_CODE_MISSING_TOKEN = "AUTH_TOKEN_MISSING"
ERROR_CODE_INVALID_TOKEN_FORMAT = "AUTH_TOKEN_FORMAT_INVALID"
ERROR_CODE_INVALID_OR_EXPIRED_TOKEN = "AUTH_TOKEN_INVALID_OR_EXPIRED"
ERROR_CODE_MISSING_AUTH_CONTEXT = "AUTH_CONTEXT_MISSING"
ERROR_CODE_AUTH_USER_NOT_FOUND = "AUTH_USER_NOT_FOUND"


def error_detail(*, code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def raise_http_error(*, status_code: int, code: str, detail: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail=error_detail(code=code, detail=detail))


def http_exception_response_content(exc: HTTPException) -> dict[str, object]:
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code")
        detail = exc.detail.get("detail")
        if isinstance(code, str) and isinstance(detail, str):
            return {"code": code, "detail": detail}

    return {"code": f"HTTP_{exc.status_code}", "detail": exc.detail}
