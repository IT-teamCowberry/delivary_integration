import json

import frappe
import requests


class DelhiveryAPI:
    DEFAULT_PATHS = {
        "pincode_check_path": "/c/api/pin-codes/json/",
        "waybill_fetch_path": "/waybill/api/bulk/json/",
        "shipping_charge_path": "/api/kinko/v1/invoice/charges/.json",
        "create_shipment_path": "/api/cmu/create.json",
        "track_shipment_path": "/api/v1/packages/json/",
        "cancel_shipment_path": "/api/p/edit",
        "packing_slip_path": "/api/p/packing_slip",
    }
    DEFAULT_TRACKING_URL_TEMPLATE = "https://www.delhivery.com/track/package/{waybill}"

    def __init__(self):
        settings = frappe.get_single("Delhivery Settings")
        if not settings.enabled:
            frappe.throw("Delhivery integration is disabled. Enable it in Delhivery Settings.")

        self.settings = settings
        self.token = settings.get_password("api_token")
        self.client_name = settings.client_name
        self.timeout = 30

        # Resolve base URL from settings (sandbox/production)
        if settings.environment == "Production":
            base = settings.production_base_url
        else:
            base = settings.sandbox_base_url
        if not base:
            frappe.throw(
                f"{settings.environment} Base URL is not configured in Delhivery Settings."
            )
        self.base_url = base.rstrip("/")

    def _path(self, key):
        """Resolve an endpoint path from settings, falling back to default."""
        return getattr(self.settings, key, None) or self.DEFAULT_PATHS[key]

    def tracking_url(self, waybill):
        template = self.settings.tracking_url_template or self.DEFAULT_TRACKING_URL_TEMPLATE
        return template.format(waybill=waybill)

    @property
    def headers(self):
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get(self, endpoint, params=None):
        try:
            resp = requests.get(
                f"{self.base_url}{endpoint}",
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Request timed out"}
        except requests.exceptions.HTTPError as e:
            return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _post(self, endpoint, data=None, raw=False):
        try:
            if raw:
                resp = requests.post(
                    f"{self.base_url}{endpoint}",
                    headers={"Authorization": f"Token {self.token}", "Accept": "application/json"},
                    data=data,
                    timeout=self.timeout,
                )
            else:
                resp = requests.post(
                    f"{self.base_url}{endpoint}",
                    headers=self.headers,
                    data=json.dumps(data) if data else None,
                    timeout=self.timeout,
                )
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Request timed out"}
        except requests.exceptions.HTTPError as e:
            return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_pincode(self, pincode):
        result = self._get(self._path("pincode_check_path"), params={"filter_codes": pincode})
        if result["success"]:
            codes = result["data"].get("delivery_codes", [])
            return {"success": True, "serviceable": len(codes) > 0, "data": codes}
        return result

    def fetch_waybill(self, count=1):
        return self._get(
            self._path("waybill_fetch_path"),
            params={"cl": self.client_name, "count": count},
        )

    def fetch_shipping_charge(self, origin_pin, dest_pin, weight_grams, cod_amount=0, mode=None):
        params = {
            "md": mode or getattr(self.settings, "default_shipping_mode", None) or "E",
            "cgm": weight_grams,
            "o_pin": origin_pin,
            "d_pin": dest_pin,
            "ss": "Delivered",
        }
        if cod_amount:
            params["cod"] = cod_amount
        return self._get(self._path("shipping_charge_path"), params=params)

    def create_shipment(self, shipment_data, pickup_location):
        payload = {
            "format": "json",
            "data": json.dumps(
                {
                    "shipments": [shipment_data],
                    "pickup_location": {"name": pickup_location},
                }
            ),
        }
        result = self._post(self._path("create_shipment_path"), data=payload, raw=True)
        if not result.get("success"):
            return result

        body = result.get("data") or {}
        packages = body.get("packages") or []
        pkg = packages[0] if packages else {}
        pkg_status = (pkg.get("status") or "").lower()

        if body.get("success") is False or pkg_status == "fail":
            remarks = pkg.get("remarks") or []
            error_msg = (
                "; ".join(remarks)
                or body.get("rmk")
                or "Delhivery rejected the shipment (no remarks)."
            )
            return {"success": False, "error": error_msg, "data": body}

        return result

    def track_shipment(self, waybill):
        return self._get(self._path("track_shipment_path"), params={"waybill": waybill})

    def cancel_shipment(self, waybill):
        return self._post(
            self._path("cancel_shipment_path"),
            data={"waybill": waybill, "cancellation": "true"},
        )

    def get_packing_slip(self, waybill):
        try:
            resp = requests.get(
                f"{self.base_url}{self._path('packing_slip_path')}",
                headers={"Authorization": f"Token {self.token}"},
                params={"wbns": waybill, "pdf": "true"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").lower()
            content = resp.content

            if "application/pdf" in content_type or content[:4] == b"%PDF":
                return {"success": True, "data": content, "kind": "pdf"}

            try:
                payload = resp.json()
            except ValueError:
                return {"success": False, "error": f"Unexpected response: {resp.text[:300]}"}

            packages = payload.get("packages") if isinstance(payload, dict) else None
            if packages and isinstance(packages, list):
                pkg = packages[0]
                pdf_url = pkg.get("pdf_download_link") or pkg.get("pdf_link") or pkg.get("pod")
                if pdf_url:
                    pdf_resp = requests.get(pdf_url, timeout=self.timeout)
                    pdf_resp.raise_for_status()
                    if pdf_resp.content[:4] == b"%PDF":
                        return {"success": True, "data": pdf_resp.content, "kind": "pdf"}
                    return {"success": False, "error": "Linked file is not a valid PDF"}

            error_msg = (
                payload.get("error")
                or payload.get("message")
                or payload.get("rmk")
                or json.dumps(payload)[:300]
            )
            return {"success": False, "error": f"Delhivery: {error_msg}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
