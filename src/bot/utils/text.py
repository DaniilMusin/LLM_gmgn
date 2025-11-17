import re
CASHTAG = re.compile(r"\$[A-Z0-9]{2,10}")

def extract_symbols(text: str) -> list[str]:
    return [m.group()[1:] for m in CASHTAG.finditer((text or "").upper())]
