"""Access failures preserve refresh recovery; revoked sessions still clear cookies."""

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.modules.identity.http_security import error_response
from app.modules.identity.types import AuthError


@pytest.mark.parametrize(
    "path,code,clears_cookies",
    [
        ("/auth/me", "invalid_token", False),
        ("/conversations/example/messages", "invalid_token", False),
        ("/auth/refresh", "invalid_token", True),
        ("/auth/me", "invalid_session", True),
        ("/auth/refresh", "refresh_reused", True),
    ],
)
def test_cookie_policy_allows_access_recovery(path, code, clears_cookies):
    settings = SimpleNamespace(cookie_name=lambda kind: f"test_{kind}", secure_cookies=True)
    app = SimpleNamespace(state=SimpleNamespace(authentication=SimpleNamespace(settings=settings)))
    request = Request({"type": "http", "method": "GET", "path": path, "headers": [], "app": app})
    response = error_response(AuthError(code), request)
    assert response.status_code == 401
    cookies = response.headers.getlist("set-cookie")
    if clears_cookies:
        assert len(cookies) == 4
        assert all("Max-Age=0" in cookie for cookie in cookies)
    else:
        # A delayed access 401 must not remove cookies installed by another
        # request's successful refresh response.
        assert cookies == []
