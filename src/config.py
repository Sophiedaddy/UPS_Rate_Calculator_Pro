import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)

UPS_CLIENT_ID = os.getenv("UPS_CLIENT_ID")
UPS_CLIENT_SECRET = os.getenv("UPS_CLIENT_SECRET")
UPS_SHIPPER_NUMBER = os.getenv("UPS_SHIPPER_NUMBER")

if not UPS_CLIENT_ID:
    raise RuntimeError(
        ".env 파일에 UPS_CLIENT_ID가 설정되지 않았습니다."
    )

if not UPS_CLIENT_SECRET:
    raise RuntimeError(
        ".env 파일에 UPS_CLIENT_SECRET이 설정되지 않았습니다."
    )

if not UPS_SHIPPER_NUMBER:
    raise RuntimeError(
        ".env 파일에 UPS_SHIPPER_NUMBER가 설정되지 않았습니다."
    )