"""Xac thuc: ai dang goi.

Tren Cloud Run co IAP, moi request deu mang header
`x-goog-iap-jwt-assertion`. Phai verify chu ky cua no — KHONG duoc tin
header `x-goog-authenticated-user-email`, vi header do gia duoc neu ai
do goi thang vao URL run.app ma khong qua IAP.

Khi require_iap = False (local, hoac IAP chua bat duoc vi project khong
thuoc Organization), danh tinh lay tu header X-Dev-User. Duong nay chi
duoc mo o moi truong khong co du lieu that.
"""

from fastapi import HTTPException, Request

from .settings import settings

IAP_HEADER = "x-goog-iap-jwt-assertion"
IAP_ISSUER = "https://cloud.google.com/iap"
DEV_HEADER = "x-dev-user"


def _verify_iap_jwt(token: str) -> str:
    """Tra ve email trong JWT sau khi da verify chu ky.

    Dung khoa cong khai cua Google, kiem ca issuer lan audience.
    """
    from google.auth.transport import requests as ga_requests
    from google.oauth2 import id_token

    try:
        payload = id_token.verify_token(
            token,
            ga_requests.Request(),
            audience=settings.iap_audience or None,
            certs_url="https://www.gstatic.com/iap/verify/public_key",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, f"IAP JWT khong hop le: {exc}") from exc

    if payload.get("iss") != IAP_ISSUER:
        raise HTTPException(401, f"issuer sai: {payload.get('iss')}")

    email = payload.get("email")
    if not email:
        raise HTTPException(401, "IAP JWT khong co email")
    return email.lower()


def caller_email(request: Request) -> str:
    if settings.require_iap:
        token = request.headers.get(IAP_HEADER)
        if not token:
            # Goi thang vao run.app, bo qua IAP -> chan tai day.
            raise HTTPException(401, "thieu IAP assertion")
        return _verify_iap_jwt(token)

    email = request.headers.get(DEV_HEADER)
    if not email:
        raise HTTPException(401, f"thieu header {DEV_HEADER} (che do dev)")
    return email.strip().lower()
