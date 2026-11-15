"""Probe Kling auth with read-only GETs. Never prints the key."""
import httpx, pathlib
KEY = pathlib.Path(r"D:\unity-text-to-anim\.cache\secrets\kling.key").read_text().strip()
bases = ["https://api-singapore.klingai.com", "https://api.klingai.com", "https://api-beijing.klingai.com"]
paths = ["/v1/images/generations?pageNum=1&pageSize=1", "/v1/videos/motion-control?pageNum=1&pageSize=1", "/account/costs"]
for b in bases:
    for p in paths:
        try:
            r = httpx.get(b + p, headers={"Authorization": f"Bearer {KEY}"}, timeout=20)
            print(b, p.split("?")[0], r.status_code, r.text[:200].replace(KEY, "<KEY>"))
        except Exception as e:
            print(b, p, "ERR", type(e).__name__, str(e)[:100])
