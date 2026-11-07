import datetime
import hashlib
import hmac
import json
import secrets
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction as db_transaction


PAYU_URLS = {
    "TEST": "https://test.payu.in/_payment",
    "LIVE": "https://secure.payu.in/_payment",
}

PAYU_WEBSERVICE_URLS = {
    "TEST": "https://test.payu.in/merchant/postservice.php?form=2",
    "LIVE": "https://info.payu.in/merchant/postservice.php?form=2",
}


def get_payu_config():
    mode = (getattr(settings, "PAYU_MODE", "TEST") or "TEST").upper()
    if mode not in PAYU_URLS:
        mode = "TEST"
    return {
        "key": getattr(settings, "PAYU_MERCHANT_KEY", "") or "",
        "salt": getattr(settings, "PAYU_MERCHANT_SALT", "") or "",
        "client_id": getattr(settings, "PAYU_CLIENT_ID", "") or "",
        "client_secret": getattr(settings, "PAYU_CLIENT_SECRET", "") or "",
        "mode": mode,
        "action_url": PAYU_URLS[mode],
        "webservice_url": PAYU_WEBSERVICE_URLS[mode],
        "success_redirect_url": getattr(settings, "PAYU_SUCCESS_REDIRECT_URL", "") or "",
        "failure_redirect_url": getattr(settings, "PAYU_FAILURE_REDIRECT_URL", "") or "",
    }


def format_payu_amount(amount) -> str:
    """Formats a Decimal/float amount to PayU's required 2-decimal string (e.g. '150.00')."""
    dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{dec:.2f}"


def generate_txnid(prefix: str = "P") -> str:
    """
    Generates a strictly alphanumeric PayU transaction ID (20 chars, <= 25 chars, no hyphens).
    Example: P261106180000A1B2C3D
    """
    import uuid
    from django.utils import timezone

    clean_prefix = "".join(ch for ch in (prefix or "P") if ch.isalnum()).upper()[:3] or "P"
    now = timezone.now()
    rand_len = max(4, min(7, 25 - len(clean_prefix) - 12))
    return f"{clean_prefix}{now.strftime('%y%m%d%H%M%S')}{uuid.uuid4().hex[:rand_len].upper()}"


def build_user_credentials(merchant_key: str, user_identifier: str) -> str:
    """
    Builds PayU CoreSDK `user_credentials` in the format `merchant_key:user_id`.
    Used by Seamless SDK to fetch saved cards, payment options, and UPI details.
    """
    clean_id = (user_identifier or "").strip()
    if not clean_id:
        return "default"
    return f"{merchant_key}:{clean_id}"


def calculate_request_hash(params: dict, salt: str | None = None) -> str:
    """
    Computes PayU SHA-512 payment request hash (`paymentHash`):
    sha512(key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||SALT)
    """
    cfg = get_payu_config()
    merchant_salt = salt if salt is not None else cfg["salt"]
    parts = [
        str(params.get("key", cfg["key"]) or ""),
        str(params.get("txnid", "") or ""),
        str(params.get("amount", "") or ""),
        str(params.get("productinfo", "") or ""),
        str(params.get("firstname", "") or ""),
        str(params.get("email", "") or ""),
        str(params.get("udf1", "") or ""),
        str(params.get("udf2", "") or ""),
        str(params.get("udf3", "") or ""),
        str(params.get("udf4", "") or ""),
        str(params.get("udf5", "") or ""),
        "",
        "",
        "",
        "",
        "",
        str(merchant_salt),
    ]
    hash_string = "|".join(parts)
    return hashlib.sha512(hash_string.encode("utf-8")).hexdigest().lower()


def calculate_command_hash(
    command: str,
    var1: str = "default",
    key: str | None = None,
    salt: str | None = None,
) -> str:
    """
    Computes PayU WebService & CoreSDK Seamless static/command hash:
    sha512(key|command|var1|SALT)

    Used by iOS/Android CoreSDK Seamless Integration for:
      - vas_for_mobile_sdk (var1="default")
      - payment_related_details_for_mobile_sdk (var1=user_credentials or "default")
      - verify_payment (var1=txnid)
      - validateVPA (var1=vpa)
      - check_is_domestic (var1=card_bin)
      - get_user_cards / save_user_card / edit_user_card / delete_user_card (var1=user_credentials)
      - getEmiAmountAccordingToInterest / eligibleBinsForEMI
    """
    cfg = get_payu_config()
    merchant_key = key if key is not None else cfg["key"]
    merchant_salt = salt if salt is not None else cfg["salt"]
    hash_string = f"{merchant_key}|{command}|{var1}|{merchant_salt}"
    return hashlib.sha512(hash_string.encode("utf-8")).hexdigest().lower()


def generate_seamless_sdk_hashes(
    params: dict,
    user_credentials: str = "default",
    key: str | None = None,
    salt: str | None = None,
) -> dict:
    """
    Pre-computes the full `PayUHashes` dictionary required by PayU CoreSDK Seamless
    Integration (iOS `PayUModelHashes` / Android `PayUHashes` / React Native / Flutter).
    """
    cfg = get_payu_config()
    merchant_key = key if key is not None else cfg["key"]
    merchant_salt = salt if salt is not None else cfg["salt"]
    txnid = str(params.get("txnid", "") or "")
    amount = str(params.get("amount", "") or "")
    user_cred = user_credentials or "default"

    payment_hash = calculate_request_hash(params, salt=merchant_salt)
    vas_hash = calculate_command_hash(
        "vas_for_mobile_sdk", "default", key=merchant_key, salt=merchant_salt
    )
    payment_details_hash = calculate_command_hash(
        "payment_related_details_for_mobile_sdk",
        user_cred,
        key=merchant_key,
        salt=merchant_salt,
    )
    payment_details_default_hash = calculate_command_hash(
        "payment_related_details_for_mobile_sdk",
        "default",
        key=merchant_key,
        salt=merchant_salt,
    )
    verify_payment_hash = calculate_command_hash(
        "verify_payment", txnid, key=merchant_key, salt=merchant_salt
    )
    get_user_cards_hash = calculate_command_hash(
        "get_user_cards", user_cred, key=merchant_key, salt=merchant_salt
    )
    save_user_card_hash = calculate_command_hash(
        "save_user_card", user_cred, key=merchant_key, salt=merchant_salt
    )
    edit_user_card_hash = calculate_command_hash(
        "edit_user_card", user_cred, key=merchant_key, salt=merchant_salt
    )
    delete_user_card_hash = calculate_command_hash(
        "delete_user_card", user_cred, key=merchant_key, salt=merchant_salt
    )
    emi_hash = calculate_command_hash(
        "getEmiAmountAccordingToInterest", amount, key=merchant_key, salt=merchant_salt
    )
    eligible_bins_emi_hash = calculate_command_hash(
        "eligibleBinsForEMI", "default", key=merchant_key, salt=merchant_salt
    )

    return {
        # Snake_case keys (Python / Android / REST convention)
        "payment_hash": payment_hash,
        "vas_for_mobile_sdk_hash": vas_hash,
        "payment_related_details_for_mobile_sdk_hash": payment_details_hash,
        "payment_related_details_for_mobile_sdk_default_hash": payment_details_default_hash,
        "verify_payment_hash": verify_payment_hash,
        "get_user_cards_hash": get_user_cards_hash,
        "save_user_card_hash": save_user_card_hash,
        "edit_user_card_hash": edit_user_card_hash,
        "delete_user_card_hash": delete_user_card_hash,
        "emi_amount_according_to_interest_hash": emi_hash,
        "eligible_bins_for_emi_hash": eligible_bins_emi_hash,
        # CamelCase aliases matching iOS `PayUModelHashes` property names directly
        "paymentHash": payment_hash,
        "VASForMobileSDKHash": vas_hash,
        "paymentRelatedDetailsForMobileSDKHash": payment_details_hash,
        "verifyPaymentHash": verify_payment_hash,
        "getUserCardsHash": get_user_cards_hash,
        "saveUserCardHash": save_user_card_hash,
        "editUserCardHash": edit_user_card_hash,
        "deleteUserCardHash": delete_user_card_hash,
    }


def calculate_response_hash(payload: dict, salt: str | None = None) -> str:
    """
    Computes PayU SHA-512 reverse response hash:
    sha512([additionalCharges|]SALT|status||||||udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key)
    """
    cfg = get_payu_config()
    merchant_salt = salt if salt is not None else cfg["salt"]

    parts = [
        str(merchant_salt),
        str(payload.get("status", "") or ""),
        "",
        "",
        "",
        "",
        "",
        str(payload.get("udf5", "") or ""),
        str(payload.get("udf4", "") or ""),
        str(payload.get("udf3", "") or ""),
        str(payload.get("udf2", "") or ""),
        str(payload.get("udf1", "") or ""),
        str(payload.get("email", "") or ""),
        str(payload.get("firstname", "") or ""),
        str(payload.get("productinfo", "") or ""),
        str(payload.get("amount", "") or ""),
        str(payload.get("txnid", "") or ""),
        str(payload.get("key", cfg["key"]) or ""),
    ]
    additional_charges = payload.get("additionalCharges") or payload.get("additional_charges")
    if additional_charges:
        parts.insert(0, str(additional_charges))

    hash_string = "|".join(parts)
    return hashlib.sha512(hash_string.encode("utf-8")).hexdigest().lower()


def verify_response_hash(payload: dict, salt: str | None = None) -> bool:
    """Constant-time verification of PayU's response hash."""
    received_hash = str(payload.get("hash", "") or "").strip().lower()
    if not received_hash:
        return False
    expected_hash = calculate_response_hash(payload, salt=salt)
    return hmac.compare_digest(received_hash, expected_hash)


def generate_mobile_sdk_hash(
    hash_string: str, post_salt: str | None = None, salt: str | None = None
) -> str:
    """
    Generates dynamic hash required by PayU Mobile SDK (`generateHash` callback).
    Handles `hashString` whether or not it already ends with a trailing pipe `|`.
    """
    cfg = get_payu_config()
    merchant_salt = salt if salt is not None else cfg["salt"]
    base = str(hash_string)
    if not base.endswith("|"):
        base = f"{base}|"
    full_string = f"{base}{merchant_salt}"
    if post_salt:
        full_string = (
            f"{full_string}|{post_salt}"
            if not full_string.endswith("|")
            else f"{full_string}{post_salt}"
        )
    return hashlib.sha512(full_string.encode("utf-8")).hexdigest().lower()


def fetch_payu_verify_payment(txnid: str) -> dict:
    """
    Calls PayU's server-to-server `verify_payment` WebService API (`postservice.php?form=2`)
    to pull the authoritative status of `txnid` directly from PayU.
    """
    cfg = get_payu_config()
    if not cfg["key"] or not cfg["salt"]:
        raise RuntimeError("PayU gateway credentials are not configured.")

    cmd = "verify_payment"
    cmd_hash = calculate_command_hash(cmd, txnid, key=cfg["key"], salt=cfg["salt"])
    form_data = urllib.parse.urlencode(
        {
            "key": cfg["key"],
            "command": cmd,
            "var1": txnid,
            "hash": cmd_hash,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        cfg["webservice_url"],
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def estimate_subscription_amount(subscription, days: int = 30) -> Decimal:
    """
    Computes the default upfront amount for a subscription over its active period
    (or next `days` calendar days starting from subscription.start_date) based on
    customer-specific product pricing or standard product unit_price.
    """
    from inventory.models import CustomerProductPrice

    daily_cost = Decimal("0.00")
    customer = subscription.customer
    for item in subscription.items.select_related("product").all():
        custom = CustomerProductPrice.objects.filter(
            customer=customer, product=item.product
        ).first()
        unit_price = custom.custom_price if custom else item.product.unit_price
        daily_cost += item.quantity * Decimal(str(unit_price))

    if daily_cost <= Decimal("0.00"):
        return Decimal("0.00")

    start = subscription.start_date
    if subscription.end_date and subscription.end_date >= start:
        total_days = (subscription.end_date - start).days + 1
    else:
        total_days = days

    delivery_days = 0
    for offset in range(total_days):
        target_date = start + datetime.timedelta(days=offset)
        if subscription.should_deliver_on(target_date):
            delivery_days += 1

    # Fallback to at least 1 delivery day if subscription is currently paused
    if delivery_days == 0:
        delivery_days = 1

    return (daily_cost * Decimal(delivery_days)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def reconcile_payu_callback(payload: dict) -> tuple:
    """
    Processes a verified PayU callback/webhook/verify_payment payload inside the
    appropriate tenant schema.
    Returns (payment, outcome_str) where outcome_str is 'verified', 'rejected', or 'already_processed'.
    """
    from django_tenants.utils import schema_context
    from .models import OnlinePayment, OnlinePaymentStatus

    txnid = str(payload.get("txnid", "") or "").strip()
    payment_id = str(payload.get("udf2", "") or "").strip()
    schema_name = str(payload.get("udf1", "") or "").strip()
    payu_status = str(payload.get("status", "") or "").strip().lower()
    mihpayid = str(payload.get("mihpayid", "") or "").strip()
    bank_ref_num = str(payload.get("bank_ref_num", "") or "").strip()
    mode = str(payload.get("mode", "") or "").strip()
    error_msg = (
        str(
            payload.get("error_Message")
            or payload.get("field9")
            or payload.get("unmappedstatus")
            or "Payment failed"
        ).strip()
    )

    def _process():
        with db_transaction.atomic():
            qs = OnlinePayment.objects.select_for_update()
            payment = None
            if txnid:
                payment = qs.filter(gateway_txnid=txnid).first()
            if not payment and payment_id:
                payment = qs.filter(id=payment_id).first()
            if not payment:
                return None, "not_found"

            # Save gateway metadata
            payment.gateway_mihpayid = mihpayid or payment.gateway_mihpayid
            payment.gateway_mode = mode or payment.gateway_mode
            if bank_ref_num or mihpayid:
                payment.transaction_id = bank_ref_num or mihpayid
            payment.gateway_raw_response = dict(payload)

            # Idempotency guard: if already verified, just update metadata and return
            if payment.status == OnlinePaymentStatus.VERIFIED:
                payment.save(
                    update_fields=[
                        "gateway_mihpayid",
                        "gateway_mode",
                        "transaction_id",
                        "gateway_raw_response",
                    ]
                )
                return payment, "already_processed"

            if payu_status == "success":
                payment.save(
                    update_fields=[
                        "gateway_mihpayid",
                        "gateway_mode",
                        "transaction_id",
                        "gateway_raw_response",
                    ]
                )
                payment.verify(user=None)
                return payment, "verified"
            else:
                payment.save(
                    update_fields=[
                        "gateway_mihpayid",
                        "gateway_mode",
                        "transaction_id",
                        "gateway_raw_response",
                    ]
                )
                payment.reject(user=None, reason=error_msg)
                return payment, "rejected"

    if schema_name:
        with schema_context(schema_name):
            return _process()
    return _process()
