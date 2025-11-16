import base64, httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import to_bytes_versioned
API = "https://gmgn.ai"
async def gmgn_get_route_sol(token_in: str, token_out: str, in_amount: int,
                             from_addr: str, slippage_pct: float, is_anti_mev: bool = False, fee_sol: float | None = None) -> dict:
    params = {"token_in_address": token_in, "token_out_address": token_out,
              "in_amount": str(in_amount), "from_address": from_addr, "slippage": slippage_pct}
    if is_anti_mev: params["is_anti_mev"] = "true"
    if fee_sol is not None: params["fee"] = fee_sol
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.get(f"{API}/defi/router/v1/sol/tx/get_swap_route", params=params); r.raise_for_status(); return r.json()
def sol_sign_tx_base64(unsigned_b64: str, payer_b58: str) -> str:
    raw = VersionedTransaction.from_bytes(base64.b64decode(unsigned_b64)); payer = Keypair.from_base58_string(payer_b58)
    if hasattr(raw, "sign"):
        raw.sign([payer]); return base64.b64encode(bytes(raw)).decode()
    sigs = list(raw.signatures); msg_bytes = to_bytes_versioned(raw.message)
    sigs[0] = payer.sign_message(msg_bytes); raw.signatures = tuple(sigs)
    return base64.b64encode(bytes(raw)).decode()
async def gmgn_send_tx_sol(signed_b64: str, anti_mev: bool = False) -> dict:
    payload = {"chain":"sol","signedTx":signed_b64}
    if anti_mev: payload["isAntiMev"] = True
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.post(f"{API}/txproxy/v1/send_transaction", json=payload); r.raise_for_status(); return r.json()
async def gmgn_poll_status(hash_str: str, last_valid_height: int) -> dict:
    params = {"hash": hash_str, "last_valid_height": last_valid_height}
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.get(f"{API}/defi/router/v1/sol/tx/get_transaction_status", params=params); r.raise_for_status(); return r.json()
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qJkF8ouRfn7YNnW9nRybmC6AZ"
LAMPORTS = 10**9
def sol_to_lamports(sol: float) -> int: return int(sol * LAMPORTS)
