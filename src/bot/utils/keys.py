import os, yaml
KEYS_PATH = os.environ.get("KEYS_PATH", "config/keys.yaml")
def load_keys(provider: str) -> list[str]:
    try:
        with open(KEYS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        arr = (data.get(provider, {}) or {}).get("api_keys", []) or []
    except Exception:
        arr = []
    if provider == "perplexity":
        env = os.environ.get("PPLX_API_KEYS", "")
        if env: arr = [x.strip() for x in env.split(",") if x.strip()]
    return [k for k in arr if isinstance(k, str) and k]
