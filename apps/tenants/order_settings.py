from decimal import Decimal, InvalidOperation

DEFAULTS = {
    "minimum_order_enabled": False,
    "minimum_order_value": "0.00",
    "minimum_order_basis": "subtotal",
    "fulfillment_mode": "both",
}

def get_order_settings(tenant):
    root = tenant.settings if isinstance(tenant.settings, dict) else {}
    saved = root.get("orders", {})
    if not isinstance(saved, dict):
        saved = {}
    result = {**DEFAULTS, **saved}
    try:
        value = Decimal(str(result["minimum_order_value"]))
        if not value.is_finite() or value < 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        value = Decimal("0.00")
    result["minimum_order_value"] = value.quantize(Decimal("0.01"))
    if result["minimum_order_basis"] != "subtotal":
        result["minimum_order_basis"] = "subtotal"
    if result["fulfillment_mode"] not in ("delivery", "pickup", "both"):
        result["fulfillment_mode"] = "both"
    result["minimum_order_enabled"] = bool(result["minimum_order_enabled"])
    return result


def save_order_settings(tenant, *, enabled, value, fulfillment_mode):
    try:
        amount = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Informe um valor mínimo válido.")
    if not amount.is_finite() or amount < 0:
        raise ValueError("O valor mínimo não pode ser negativo.")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Utilize no máximo duas casas decimais.")
    if fulfillment_mode not in ("delivery", "pickup", "both"):
        raise ValueError("Selecione uma modalidade de atendimento válida.")

    root = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    current = dict(root.get("orders") or {})
    current.update({
        "minimum_order_enabled": bool(enabled),
        "minimum_order_value": format(amount, ".2f"),
        "minimum_order_basis": "subtotal",
        "fulfillment_mode": fulfillment_mode,
    })
    root["orders"] = current
    tenant.settings = root
    tenant.save(update_fields=["settings", "updated_at"])
    return amount
