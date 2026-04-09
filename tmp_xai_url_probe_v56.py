import json
import sys
import urllib.error
import urllib.request


URL = "http://127.0.0.1:8787/api/battle_from_x_url"
PAYLOAD = {
    "url": "https://x.com/majan_saitou/status/2039145221930598745?s=20",
}


def main() -> int:
    request = urllib.request.Request(
        URL,
        data=json.dumps(PAYLOAD).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
        print(body)
        return 0
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
