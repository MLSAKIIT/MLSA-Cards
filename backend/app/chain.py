from functools import lru_cache
from typing import Optional, Dict, Any
import logging
from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.types import Wei, TxReceipt, TxParams
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress

from .config import get_settings

# Configure logging
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_web3() -> Web3:
    settings = get_settings()

    if not settings.rpc_url:
        raise RuntimeError("RPC_URL is not configured. Please set it in your .env file")

    try:
        w3 = Web3(Web3.HTTPProvider(
            settings.rpc_url,
            request_kwargs={'timeout': 30}  # Add timeout for better reliability
        ))

        # Required for Hardhat, Sepolia, Polygon, Amoy
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        # Verify connection
        if not w3.is_connected():
            raise RuntimeError(f"Web3 RPC not reachable at: {settings.rpc_url}")

        # Log connection info
        chain_id = w3.eth.chain_id
        block_number = w3.eth.block_number
        logger.info(f"Connected to Web3 - Chain ID: {chain_id}, Block: {block_number}")

        return w3

    except Exception as e:
        logger.error(f"Failed to initialize Web3: {str(e)}")
        raise RuntimeError(f"Web3 initialization failed: {str(e)}") from e


@lru_cache(maxsize=1)
def get_signer() -> LocalAccount:
    settings = get_settings()

    if not settings.private_key:
        raise RuntimeError("PRIVATE_KEY is not set in environment variables")

    try:
        # Validate private key format
        if settings.private_key.startswith('0x'):
            private_key = settings.private_key
        else:
            private_key = f"0x{settings.private_key}"

        account = Account.from_key(private_key)
        logger.info(f"Signer initialized: {account.address}")

        return account

    except Exception as e:
        logger.error(f"Invalid PRIVATE_KEY format: {str(e)}")
        raise RuntimeError("Invalid PRIVATE_KEY format. Ensure it's a valid Ethereum private key") from e


def get_signer_address() -> ChecksumAddress:
    return Web3.to_checksum_address(get_signer().address)


def get_chain_id() -> int:
    return get_web3().eth.chain_id


def get_network_name() -> str:
    chain_id = get_chain_id()
    network_map = {
        1: "Ethereum Mainnet",
        5: "Goerli Testnet",
        11155111: "Sepolia Testnet",
        137: "Polygon Mainnet",
        80002: "Polygon Amoy Testnet",
        80001: "Mumbai Testnet (deprecated)",
        31337: "Hardhat Local",
        1337: "Ganache Local",
    }
    return network_map.get(chain_id, f"Unknown Network (Chain ID: {chain_id})")


def get_balance(address: str) -> Wei:
    w3 = get_web3()
    checksum_addr = Web3.to_checksum_address(address)
    return w3.eth.get_balance(checksum_addr)


def get_balance_ether(address: str) -> float:
    w3 = get_web3()
    balance_wei = get_balance(address)
    return float(w3.from_wei(balance_wei, 'ether'))


def get_signer_balance() -> float:
    return get_balance_ether(get_signer_address())


def get_gas_price() -> Wei:
    w3 = get_web3()
    return w3.eth.gas_price


def estimate_gas(transaction: TxParams) -> int:
    w3 = get_web3()
    return w3.eth.estimate_gas(transaction)


def get_transaction_receipt(tx_hash: str) -> Optional[TxReceipt]:
    w3 = get_web3()
    try:
        if not tx_hash.startswith('0x'):
            tx_hash = f"0x{tx_hash}"
        return w3.eth.get_transaction_receipt(tx_hash)
    except Exception as e:
        logger.warning(f"Transaction receipt not found for {tx_hash}: {str(e)}")
        return None


def wait_for_transaction(tx_hash: str, timeout: int = 120) -> TxReceipt:
    w3 = get_web3()
    if not tx_hash.startswith('0x'):
        tx_hash = f"0x{tx_hash}"

    logger.info(f"Waiting for transaction {tx_hash}...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    logger.info(f"Transaction mined in block {receipt['blockNumber']}")

    return receipt


def get_nonce(address: Optional[str] = None) -> int:
    w3 = get_web3()
    addr = address or get_signer_address()
    checksum_addr = Web3.to_checksum_address(addr)
    return w3.eth.get_transaction_count(checksum_addr)


def is_contract(address: str) -> bool:
    w3 = get_web3()
    checksum_addr = Web3.to_checksum_address(address)
    code = w3.eth.get_code(checksum_addr)
    return len(code) > 0


def get_block_number() -> int:
    w3 = get_web3()
    return w3.eth.block_number


def get_chain_info() -> Dict[str, Any]:
    w3 = get_web3()
    chain_id = get_chain_id()
    signer_address = get_signer_address()
    signer_balance = get_signer_balance()

    return {
        "connected": w3.is_connected(),
        "chain_id": chain_id,
        "network_name": get_network_name(),
        "block_number": get_block_number(),
        "gas_price_gwei": float(w3.from_wei(get_gas_price(), 'gwei')),
        "signer_address": signer_address,
        "signer_balance": f"{signer_balance:.4f}",
        "rpc_url": get_settings().rpc_url,
    }


def validate_address(address: str) -> bool:
    try:
        Web3.to_checksum_address(address)
        return True
    except Exception:
        return False


def to_checksum_address(address: str) -> ChecksumAddress:
    return Web3.to_checksum_address(address)


# Health check function
def health_check() -> Dict[str, Any]:
    try:
        info = get_chain_info()

        # Check if signer has sufficient balance
        min_balance = 0.01
        signer_balance = float(info["signer_balance"])

        status = "healthy" if signer_balance >= min_balance else "warning"
        warnings = []

        if signer_balance < min_balance:
            warnings.append(f"Low signer balance: {signer_balance:.4f} (minimum recommended: {min_balance})")

        return {
            "status": status,
            "chain": info,
            "warnings": warnings,
            "timestamp": get_web3().eth.get_block('latest')['timestamp']
        }

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "chain": None,
            "warnings": ["Blockchain connection failed"]
        }


# Export all functions
__all__ = [
    "get_web3",
    "get_signer",
    "get_signer_address",
    "get_chain_id",
    "get_network_name",
    "get_balance",
    "get_balance_ether",
    "get_signer_balance",
    "get_gas_price",
    "estimate_gas",
    "get_transaction_receipt",
    "wait_for_transaction",
    "get_nonce",
    "is_contract",
    "get_block_number",
    "get_chain_info",
    "validate_address",
    "to_checksum_address",
    "health_check",
]

