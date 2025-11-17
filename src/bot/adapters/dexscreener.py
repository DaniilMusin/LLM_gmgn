import httpx
BASE = "https://api.dexscreener.com"
async def token_info_solana(mint: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.get(f"{BASE}/latest/dex/tokens/{mint}")
        r.raise_for_status()
        return r.json()
async def search_pairs_solana(query: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.get(f"{BASE}/latest/dex/search", params={"q": query})
        r.raise_for_status()
        return r.json()
