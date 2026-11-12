"""
routers/geocode.py — address -> coordinates for the "list a new space" form
and the destination search.
  GET /geocode?q=Sigra, Varanasi

Calling OpenStreetMap Nominatim from the server avoids CORS and lets us
follow its usage policy: an identifying User-Agent, at most about one
request per second, and caching repeated lookups.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from utils.rate_limit import client_ip, geocode_by_ip

router = APIRouter(tags=["geocode"])

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ParkWise/1.0 (parking marketplace; geocoding owner listings)"

_CACHE_SIZE = 500
_cache: "OrderedDict[str, Optional[dict]]" = OrderedDict()
_lock = threading.Lock()
_last_call = 0.0


def _cache_get(key: str):
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return True, _cache[key]
    return False, None


def _cache_put(key: str, value: Optional[dict]) -> None:
    with _lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)


def _wait_for_turn() -> None:
    """Keep calls to Nominatim at least 1 second apart (their policy)."""
    global _last_call
    with _lock:
        wait = 1.0 - (time.monotonic() - _last_call)
        _last_call = time.monotonic() + max(wait, 0)
    if wait > 0:
        time.sleep(wait)


# A plain `def` (not async) — FastAPI runs it in a thread pool, so the
# blocking urllib call doesn't stall other requests.
@router.get("/geocode")
def geocode(request: Request, q: str = Query(..., min_length=2, max_length=200)) -> Optional[dict]:
    geocode_by_ip.hit(client_ip(request))

    key = " ".join(q.lower().split())
    found, cached = _cache_get(key)
    if found:
        return cached

    _wait_for_turn()
    params = urllib.parse.urlencode({"format": "json", "limit": 1, "q": q})
    req = urllib.request.Request(f"{NOMINATIM_URL}?{params}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise HTTPException(status_code=503, detail="The address lookup service is unavailable right now. Please try again in a moment.")

    result = None
    if results:
        top = results[0]
        result = {"lat": float(top["lat"]), "lng": float(top["lon"]), "label": top.get("display_name")}
    _cache_put(key, result)
    return result
