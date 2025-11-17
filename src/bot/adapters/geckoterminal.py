import httpx
BASE = "https://api.geckoterminal.com/api/v2"
async def trending_pools_solana(page=1) -> dict:
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.get(f"{BASE}/networks/solana/trending_pools", params={"page": page})
        r.raise_for_status()
        return r.json()
async def new_pools_solana(page=1) -> dict:
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.get(f"{BASE}/networks/solana/new_pools", params={"page": page})
        r.raise_for_status()
        return r.json()
