"""Verify USDC-on-Base payments on-chain (mirrors finance-kit auth-service).

Given a transaction hash, confirms it is a successful, sufficiently-confirmed
ERC-20 transfer of USDC to the store wallet of at least the required amount.
"""

import logging
import os
import requests

log = logging.getLogger(__name__)

BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
PAYMENT_WALLET = os.getenv("PAYMENT_WALLET", "").lower()
if not PAYMENT_WALLET:
    log.warning("PAYMENT_WALLET not set. On-chain verification disabled.")

_DEFAULT_TOKENS = (
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913,"  # native USDC on Base
    "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca"   # USDbC (bridged)
)
ACCEPTED_TOKENS = {
    t.strip().lower()
    for t in os.getenv("USDC_CONTRACTS", _DEFAULT_TOKENS).split(",")
    if t.strip()
}

USDC_DECIMALS = 6
MIN_CONFIRMATIONS = int(os.getenv("MIN_CONFIRMATIONS", "2"))

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _rpc(method, params):
    resp = requests.post(
        BASE_RPC_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(data["error"].get("message", "rpc error"))
    return data.get("result")


def _addr_from_topic(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def verify_usdc_payment(tx_hash: str, min_usdc: float):
    """Return (ok: bool, reason: str, amount_usdc: float)."""
    if not PAYMENT_WALLET:
        return False, "PAYMENT_WALLET not configured on server.", 0.0

    tx_hash = (tx_hash or "").strip().lower()
    if not (tx_hash.startswith("0x") and len(tx_hash) == 66):
        return False, "Invalid transaction hash.", 0.0

    try:
        receipt = _rpc("eth_getTransactionReceipt", [tx_hash])
    except Exception as exc:
        log.warning("RPC receipt error for %s: %s", tx_hash, exc)
        return False, "Could not reach the Base network. Try again in a moment.", 0.0

    if not receipt:
        return False, "Transaction not found yet — wait for it to confirm and retry.", 0.0
    if receipt.get("status") != "0x1":
        return False, "That transaction failed on-chain.", 0.0

    smallest = 0
    for entry in receipt.get("logs", []):
        topics = entry.get("topics") or []
        if (
            entry.get("address", "").lower() in ACCEPTED_TOKENS
            and len(topics) >= 3
            and topics[0].lower() == TRANSFER_TOPIC
            and _addr_from_topic(topics[2]) == PAYMENT_WALLET
        ):
            try:
                smallest += int(entry.get("data", "0x0"), 16)
            except ValueError:
                continue

    if smallest == 0:
        return False, "No USDC payment to the store wallet was found in this transaction.", 0.0

    amount = smallest / (10 ** USDC_DECIMALS)

    try:
        latest = int(_rpc("eth_blockNumber", []), 16)
        block = int(receipt.get("blockNumber", "0x0"), 16)
        confirmations = latest - block + 1
    except Exception:
        confirmations = MIN_CONFIRMATIONS

    if confirmations < MIN_CONFIRMATIONS:
        return (False,
                f"Payment found but only {confirmations} confirmation(s); "
                f"please wait for {MIN_CONFIRMATIONS} and retry.",
                amount)

    if amount + 1e-9 < min_usdc:
        return (False,
                f"Payment of {amount:.2f} USDC is less than the {min_usdc:.0f} USDC required for this tier.",
                amount)

    return True, "ok", amount
