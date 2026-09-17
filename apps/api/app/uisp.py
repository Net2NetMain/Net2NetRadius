import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import get_settings


def test_connection() -> dict:
    """Verify the local UISP CRM API key without returning the key or customer data."""
    settings = get_settings()
    if not settings.uisp_base_url or not settings.uisp_api_token:
        return {"configured": False, "connected": False, "detail": "UISP CRM API URL and app key are not configured"}
    url = f"{settings.uisp_base_url.rstrip('/')}/clients?limit=1"
    request = Request(url, headers={"X-Auth-App-Key": settings.uisp_api_token, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        count = len(payload) if isinstance(payload, list) else None
        return {"configured": True, "connected": True, "sample_client_count": count}
    except HTTPError as exc:
        return {"configured": True, "connected": False, "detail": f"UISP returned HTTP {exc.code}"}
    except (URLError, TimeoutError, ValueError):
        return {"configured": True, "connected": False, "detail": "Could not reach the UISP CRM API"}
