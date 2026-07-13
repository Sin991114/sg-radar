"""HTTP fetching with browser-like headers and simple retries."""
import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch(url, *, headers=None, timeout=25, retries=2):
    h = {"User-Agent": UA, "Accept-Language": "en-SG,en;q=0.9"}
    if headers:
        h.update(headers)
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=h, timeout=timeout)
            if resp.status_code == 200:
                return resp
            last_err = RuntimeError(f"HTTP {resp.status_code} for {url}")
        except requests.RequestException as e:
            last_err = e
        time.sleep(1.5 * (attempt + 1))
    raise last_err
