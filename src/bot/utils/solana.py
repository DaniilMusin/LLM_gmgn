from solders.pubkey import Pubkey

def is_valid_mint(addr: str | None) -> bool:
    if not addr: return False
    try:
        _ = Pubkey.from_string(addr); return True
    except Exception:
        return False
