from __future__ import annotations

import gzip
import ssl
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


FETCH_RETRIES = 3


class FetchSession:
    def __init__(self, max_per_host: int = 3) -> None:
        self.max_per_host = max(1, max_per_host)
        self._text_cache: dict[str, str] = {}
        self._bytes_cache: dict[str, bytes] = {}
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._host_limits: dict[str, threading.Semaphore] = {}
        self._state_lock = threading.Lock()

    @staticmethod
    def canonical_url(url: str) -> str:
        parsed = urlsplit(url)
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
        )

    def _resource_lock(self, kind: str, key: str) -> threading.Lock:
        with self._state_lock:
            return self._locks.setdefault((kind, key), threading.Lock())

    def _host_limit(self, url: str) -> threading.Semaphore:
        host = urlsplit(url).netloc
        with self._state_lock:
            return self._host_limits.setdefault(
                host,
                threading.Semaphore(self.max_per_host),
            )

    def get_text(self, url: str, loader) -> str:
        key = self.canonical_url(url)
        with self._resource_lock("text", key):
            if key in self._text_cache:
                return self._text_cache[key]
            with self._host_limit(key):
                value = loader(key)
            self._text_cache[key] = value
            return value

    def get_bytes(self, url: str, loader) -> bytes:
        key = self.canonical_url(url)
        with self._resource_lock("bytes", key):
            if key in self._bytes_cache:
                return self._bytes_cache[key]
            with self._host_limit(key):
                value = loader(key)
            self._bytes_cache[key] = value
            return value


def decode_bytes(data: bytes, content_type: str = "") -> str:
    import re

    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    encodings = [match.group(1)] if match else []
    head = data[:4096].decode("ascii", errors="ignore")
    meta = re.search(r"<meta[^>]+charset=[\"']?\s*([\w-]+)", head, re.I)
    if meta:
        encodings.append(meta.group(1))
    encodings += ["utf-8", "gb18030", "big5"]
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="ignore")


def fetch_raw_uncached(
    url: str,
    timeout: int,
    *,
    opener=urlopen,
    sleeper=time.sleep,
) -> str:
    parsed = urlsplit(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": referer,
        },
    )
    context = ssl._create_unverified_context()
    last_error: Exception | None = None
    deadline = time.monotonic() + max(0.1, timeout)
    for attempt in range(FETCH_RETRIES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempt_timeout = max(0.1, remaining / (FETCH_RETRIES - attempt + 1))
        try:
            with opener(request, timeout=attempt_timeout, context=context) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
            return decode_bytes(raw, content_type)
        except Exception as exc:
            last_error = exc
            if isinstance(exc, HTTPError) and exc.code in {404, 410}:
                raise
            if attempt + 1 < FETCH_RETRIES:
                delay = min(
                    0.5 * (attempt + 1),
                    max(0.0, deadline - time.monotonic()),
                )
                if delay:
                    sleeper(delay)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(
            f"单URL总时限{timeout}秒已用尽：{last_error}"
        ) from last_error
    try:
        import requests
        from requests.packages.urllib3.exceptions import InsecureRequestWarning

        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        response = requests.get(
            url,
            timeout=max(0.1, remaining),
            verify=False,
            headers=dict(request.header_items()),
        )
        response.raise_for_status()
        return decode_bytes(
            response.content,
            response.headers.get("Content-Type", ""),
        )
    except Exception as requests_error:
        raise RuntimeError(
            f"urllib 请求失败：{type(last_error).__name__}: {last_error}；"
            f"requests fallback 失败：{type(requests_error).__name__}: "
            f"{requests_error}"
        ) from requests_error


def fetch_bytes_uncached(
    url: str,
    timeout: int,
    *,
    opener=urlopen,
    sleeper=time.sleep,
) -> bytes:
    parsed = urlsplit(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Encoding": "gzip",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": referer,
        },
    )
    context = ssl._create_unverified_context()
    last_error: Exception | None = None
    deadline = time.monotonic() + max(0.1, timeout)
    for attempt in range(FETCH_RETRIES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempt_timeout = max(0.1, remaining / (FETCH_RETRIES - attempt))
        try:
            with opener(request, timeout=attempt_timeout, context=context) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
            return raw
        except Exception as exc:
            last_error = exc
            if isinstance(exc, HTTPError) and exc.code in {404, 410}:
                raise
            if attempt + 1 < FETCH_RETRIES:
                delay = min(
                    0.5 * (attempt + 1),
                    max(0.0, deadline - time.monotonic()),
                )
                if delay:
                    sleeper(delay)
    if deadline - time.monotonic() <= 0:
        raise TimeoutError(
            f"图片URL总时限{timeout}秒已用尽：{last_error}"
        ) from last_error
    if last_error is None:
        raise RuntimeError("图片抓取失败但没有底层错误")
    raise last_error


def fetch_raw(
    url: str,
    timeout: int,
    session: FetchSession | None = None,
    *,
    loader=fetch_raw_uncached,
) -> str:
    canonical_url = FetchSession.canonical_url(url)
    if session is None:
        return loader(canonical_url, timeout)
    return session.get_text(
        canonical_url,
        lambda request_url: loader(request_url, timeout),
    )


def fetch_bytes(
    url: str,
    timeout: int,
    session: FetchSession | None = None,
    *,
    loader=fetch_bytes_uncached,
) -> bytes:
    canonical_url = FetchSession.canonical_url(url)
    if session is None:
        return loader(canonical_url, timeout)
    return session.get_bytes(
        canonical_url,
        lambda request_url: loader(request_url, timeout),
    )
