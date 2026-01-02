import time
import secrets
import logging
import asyncio
from typing import Dict, Tuple

import jwt
from eth_account.messages import encode_defunct
from eth_account import Account

from .config import get_settings

##  AUTH config ##


# nonce lifetime in seconds (5 minutes)
NONCE_TTL = 300

# JWT expiry in seconds (24 hours)
JWT_EXPIRY_SECONDS = 86400

# wallet -> (nonce, created_at)
NONCE_STORE: Dict[str, Tuple[str, int]] = {} # kept in localMemory

# Message versioning for signature verification
AUTH_MESSAGE_VERSION = "MLSA_AUTH_V1"

# Cleanup control
_cleanup_task = None

#Authentication log
logger = logging.getLogger(__name__)


## NONCE functions ##


def generate_nonce(wallet: str) -> str:
    wallet = wallet.lower()
    nonce = secrets.token_hex(16)
    NONCE_STORE[wallet] = (nonce, int(time.time()))
    logger.debug(f"Generated nonce for wallet {wallet}")
    return nonce

def get_nonce(wallet: str):
    wallet = wallet.lower()
    return NONCE_STORE.get(wallet)


def remove_nonce(wallet: str) -> None:
    wallet = wallet.lower()
    NONCE_STORE.pop(wallet, None)
    logger.debug(f"Removed nonce for wallet {wallet}")

def verify_signature(
    wallet: str,
    nonce: str,
    signature: str,
    chain_id: int,
    app_name: str
) -> bool:
    wallet = wallet.lower()
    stored = NONCE_STORE.get(wallet)
    if not stored:
        logger.warning(f"No nonce found for wallet {wallet}")
        return False

    stored_nonce, created_at = stored

    # nonce mismatch
    if stored_nonce != nonce:
        return False

    # nonce expired
    if created_at + NONCE_TTL < time.time():
        remove_nonce(wallet)
        logger.warning(f"Expired nonce for wallet {wallet}")
        return False

    message = (
    f"{AUTH_MESSAGE_VERSION}\n"
    f"Sign in to {app_name} with wallet {wallet} "
    f"on chain {chain_id}. Nonce: {nonce}"
    )

    encoded = encode_defunct(text=message)


    try:
        recovered = Account.recover_message(encoded, signature=signature)
    except Exception as ex:
        logger.warning(f"Signature recovery failed for wallet {wallet}: {ex}")
        return False
    if recovered.lower() == wallet:
        remove_nonce(wallet)
        logger.info(f"Successfully authenticated wallet {wallet}")
        return True
    logger.warning(f"Recovered address mismatch for wallet {wallet}")
    return False


def issue_jwt(user_id: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + JWT_EXPIRY_SECONDS, "iss": "mlsa-cards-backend", "aud": "mlsa-cards-frontend"}  # 24 hours
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_jwt(token: str) -> dict:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience="mlsa-cards-frontend", issuer="mlsa-cards-backend")
    return payload


## Nonce cleanup background task ##


async def cleanup_expired_nonces():
    now = int(time.time())

    expired = [
        wallet for wallet, (nonce, created_at) in NONCE_STORE.items()
        if created_at + NONCE_TTL < now
    ]

    for wallet in expired:
        NONCE_STORE.pop(wallet, None)

    if expired:
        logger.info(f"Cleaned up {len(expired)} expired nonces")


async def _cleanup_loop():
    logger.info("Nonce cleanup loop started")
    while True:
        try:
            await cleanup_expired_nonces()
        except Exception as e:
            logger.error(f"Error in nonce cleanup: {e}")

        await asyncio.sleep(60)  # Run every 60 seconds

def start_nonce_cleanup():
    global _cleanup_task

    if _cleanup_task is not None:
        logger.warning("Nonce cleanup already running")
        return

    _cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info("Nonce cleanup background task started")


async def stop_nonce_cleanup():
    global _cleanup_task

    if _cleanup_task is None:
        return

    logger.info("Stopping nonce cleanup background task")
    _cleanup_task.cancel()
    try:
        await _cleanup_task
    except asyncio.CancelledError:
        pass
    _cleanup_task = None
    logger.info("Nonce cleanup background task stopped")

