"""The shared secret n8n sends in X-API-Key. Used by every endpoint that only n8n may call."""
import hmac
import logging

from fastapi import Header, HTTPException, Request

from app.config import api_shared_secret

logger = logging.getLogger(__name__)


def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Only n8n (which knows the shared secret) may save calls. Never open by default."""
    secret = api_shared_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="api key not configured")
    # compare_digest takes the same time however many leading characters match
    if not hmac.compare_digest(x_api_key.encode(), secret.encode()):
        logger.warning("rejected request: missing or wrong X-API-Key")
        raise HTTPException(status_code=401, detail="invalid api key")


# Caddy adds these to everything it forwards. n8n calls cdl-api directly, so its requests never carry them.
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "x-real-ip")


def require_internal_caller(request: Request) -> None:
    """For endpoints only n8n may call. A request that came through the public proxy gets the same 404 as an
    unknown path, so an outsider cannot even learn that the endpoint exists."""
    if any(header in request.headers for header in PROXY_HEADERS):
        raise HTTPException(status_code=404, detail="Not Found")
