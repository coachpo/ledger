from __future__ import annotations

from secrets import compare_digest

from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

EXEMPT_PATHS = {"/health", "/ready"}


class BearerTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, token: str) -> None:
        super().__init__(app)
        self.expected_authorization = f"Bearer {token}"

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        authorization = request.headers.get("Authorization", "")
        if not compare_digest(authorization, self.expected_authorization):
            return JSONResponse(
                {"detail": "Unauthorized"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        return await call_next(request)
