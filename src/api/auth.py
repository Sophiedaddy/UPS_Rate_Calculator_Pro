import base64
import json

from src.api.http_client import http_post
from src.config import UPS_CLIENT_ID, UPS_CLIENT_SECRET


def get_token(base_url: str) -> str:
    url = f"{base_url}/security/v1/oauth/token"

    basic_auth = base64.b64encode(
        f"{UPS_CLIENT_ID}:{UPS_CLIENT_SECRET}".encode("utf-8")
    ).decode("utf-8")

    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    status_code, response_body = http_post(
        url=url,
        headers=headers,
        data_dict={"grant_type": "client_credentials"},
        form=True,
    )

    if status_code != 200:
        raise RuntimeError(
            f"OAuth 인증 실패: HTTP {status_code}\n{response_body}"
        )

    response_data = json.loads(response_body)
    access_token = response_data.get("access_token")

    if not access_token:
        raise RuntimeError(
            f"OAuth 응답에 access_token이 없습니다.\n{response_body}"
        )

    return access_token