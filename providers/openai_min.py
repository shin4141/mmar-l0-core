import os, json, urllib.request, urllib.error

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

def _load_dotenv_if_present() -> None:
    if os.getenv(OPENAI_API_KEY_ENV):
        return
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == OPENAI_API_KEY_ENV and v:
                    os.environ[OPENAI_API_KEY_ENV] = v
                    return
    except Exception:
        return

def has_key() -> bool:
    _load_dotenv_if_present()
    return bool(os.getenv(OPENAI_API_KEY_ENV))

def responses_create(prompt: str, model: str | None = None, timeout_s: int = 60) -> str:
    _load_dotenv_if_present()
    api_key = os.getenv(OPENAI_API_KEY_ENV)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found")

    model = model or DEFAULT_MODEL
    url = "https://api.openai.com/v1/responses"
    payload = {"model": model, "input": prompt}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI HTTPError {e.code}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"OpenAI request failed: {e}") from e

    text = obj.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    out = obj.get("output", [])
    if isinstance(out, list):
        chunks = []
        for item in out:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for c in content:
                if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                    t = c.get("text") or c.get("output_text")
                    if isinstance(t, str):
                        chunks.append(t)
        if chunks:
            return "\n".join(chunks).strip()

    raise RuntimeError("OpenAI response had no text (unexpected format)")
