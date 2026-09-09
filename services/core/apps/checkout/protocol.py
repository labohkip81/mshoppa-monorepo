"""Local simulator protocol. These are NOT Stripe or M-Pesa webhook signatures."""

import hashlib
import hmac
import json
import time
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def ensure_local():
    if not settings.DEBUG or not settings.LOCAL_DUMMY_PAYMENTS:
        raise PermissionDenied("Dummy payments are disabled outside local test mode.")


def signed_headers(body):
    timestamp = str(int(time.time()))
    digest = hmac.new(
        settings.PAYMENT_SIGNING_SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Mshoppa-Timestamp": timestamp,
        "X-Mshoppa-Signature": digest,
    }


def verify_request(request):
    ensure_local()
    timestamp = request.headers.get("X-Mshoppa-Timestamp", "")
    try:
        fresh = abs(time.time() - int(timestamp)) <= 300
    except (ValueError, OverflowError):
        fresh = False
    expected = hmac.new(
        settings.PAYMENT_SIGNING_SECRET.encode(),
        timestamp.encode() + b"." + request.body,
        hashlib.sha256,
    ).hexdigest()
    if not fresh or not hmac.compare_digest(
        expected, request.headers.get("X-Mshoppa-Signature", "")
    ):
        raise PermissionDenied("Invalid or expired simulator signature.")


def signed_post(url, payload):
    ensure_local()
    body = json.dumps(payload, separators=(",", ":")).encode()
    with urlopen(
        Request(url, data=body, headers=signed_headers(body), method="POST"), timeout=8
    ) as response:
        return json.loads(response.read())
