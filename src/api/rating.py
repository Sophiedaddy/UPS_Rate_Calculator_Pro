import json
import uuid
from typing import Optional

from src.api.http_client import http_post


def _get_money(node: dict, *keys):
    current = node

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None, None

    if not isinstance(current, dict):
        return None, None

    monetary_value = (
        current.get("MonetaryValue")
        or current.get("TotalCharge", {}).get("MonetaryValue")
    )

    currency_code = (
        current.get("CurrencyCode")
        or current.get("TotalCharge", {}).get("CurrencyCode")
    )

    return monetary_value, currency_code


def summarize_rates(data: dict, service_code_map: Optional[dict] = None):
    rated_shipments = []

    if isinstance(data, dict):
        if "RateResponse" in data:
            rated_shipments = (
                data["RateResponse"].get("RatedShipment") or []
            )
        elif "RatedShipment" in data:
            rated_shipments = data.get("RatedShipment") or []

    if isinstance(rated_shipments, dict):
        rated_shipments = [rated_shipments]

    results = []

    for shipment in rated_shipments:
        if not isinstance(shipment, dict):
            continue

        service = shipment.get("Service") or {}

        service_code = (
            service.get("Code")
            if isinstance(service, dict)
            else None
        ) or shipment.get("serviceCode")

        service_description = (
            service.get("Description")
            if isinstance(service, dict)
            else None
        ) or shipment.get("serviceName")

        list_value, list_currency = _get_money(
            shipment,
            "TotalCharges",
        )

        negotiated_value = None
        negotiated_currency = None

        for key in (
            "NegotiatedRateCharges",
            "NegotiatedRates",
            "TotalShipmentCharge",
        ):
            value, currency = _get_money(shipment, key)

            if value is not None:
                negotiated_value = value
                negotiated_currency = currency
                break

        def to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        list_total = to_float(list_value)
        negotiated_total = to_float(negotiated_value)

        if (
            not service_description
            and service_code
            and service_code_map
        ):
            service_description = service_code_map.get(
                service_code,
                "",
            )

        billing_weight = None

        try:
            billing_weight = float(
                shipment.get("BillingWeight", {}).get("Weight")
            )
        except (TypeError, ValueError):
            billing_weight = None

        results.append(
            {
                "service_code": service_code or "",
                "service_desc": service_description or "",
                "currency": negotiated_currency or list_currency or "",
                "list_total": list_total,
                "negotiated_total": negotiated_total,
                "billing_weight": billing_weight,
            }
        )

    results.sort(
        key=lambda item: (
            item["negotiated_total"]
            if item["negotiated_total"] is not None
            else (
                item["list_total"]
                if item["list_total"] is not None
                else float("inf")
            )
        )
    )

    return results


def call_rating(
    base_url: str,
    access_token: str,
    shipment: dict,
) -> dict:
    url = f"{base_url}/api/rating/v2403/Shop"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "transId": uuid.uuid4().hex[:32],
        "transactionSrc": "ups-rate-calculator-pro",
    }

    payload = {
        "RateRequest": {
            "Request": {
                "TransactionReference": {
                    "CustomerContext": "ups-rate-calculator-pro"
                },
                "RequestOption": "Shop",
            },
            "Shipment": shipment,
        }
    }

    status_code, response_body = http_post(
        url=url,
        headers=headers,
        data_dict=payload,
        form=False,
    )

    if status_code >= 400:
        raise RuntimeError(
            f"Rating API 호출 실패: HTTP {status_code}\n"
            f"{response_body}"
        )

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "UPS Rating API 응답을 JSON으로 해석할 수 없습니다.\n"
            f"{response_body[:500]}"
        ) from error