import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


def build_ssl_context():
    ca_file = os.environ.get("UPS_CA_BUNDLE")
    insecure = os.environ.get("UPS_INSECURE") == "1"

    if insecure:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    if ca_file and os.path.exists(ca_file):
        return ssl.create_default_context(cafile=ca_file)

    return ssl.create_default_context()


def build_opener():
    proxy_handler = urllib.request.ProxyHandler()
    https_handler = urllib.request.HTTPSHandler(
        context=build_ssl_context()
    )

    return urllib.request.build_opener(
        proxy_handler,
        https_handler,
    )


def friendly_network_error(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        try:
            response_body = error.read().decode(
                "utf-8",
                "ignore",
            )[:400]
        except Exception:
            response_body = ""

        return (
            f"HTTP {error.code} 오류 "
            f"(URL: {error.geturl()})\n"
            f"응답: {response_body}"
        )

    if isinstance(error, urllib.error.URLError):
        reason = error.reason

        if isinstance(reason, ssl.SSLError):
            return "SSL 인증서 검증에 실패했습니다."

        if isinstance(reason, socket.gaierror):
            return "DNS 해석에 실패했습니다."

        return f"네트워크 연결 실패: {reason}"

    return str(error)


def http_post(
    url: str,
    headers: dict,
    data_dict: dict,
    form: bool = False,
):
    if form:
        request_data = urllib.parse.urlencode(
            data_dict
        ).encode("utf-8")
    else:
        request_data = json.dumps(
            data_dict
        ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=request_data,
        method="POST",
    )

    for key, value in headers.items():
        request.add_header(key, value)

    opener = build_opener()

    for attempt in range(3):
        try:
            with opener.open(request, timeout=30) as response:
                return (
                    response.getcode(),
                    response.read().decode("utf-8", "ignore"),
                )

        except Exception as error:
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue

            raise RuntimeError(
                f"urlopen error: {friendly_network_error(error)}"
            ) from error