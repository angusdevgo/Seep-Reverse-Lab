"""
HTTP 请求封装
包含 Cookie 管理、重试机制、频率控制
"""
import time
import random
import requests
from typing import Optional


class RequestClient:
    """HTTP 客户端封装"""

    def __init__(
        self,
        cookies: Optional[dict] = None,
        headers: Optional[dict] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        timeout: float = 30.0,
        retry_non_idempotent: bool = False,
    ):
        self.session = requests.Session()
        self.max_retries = max_retries
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.retry_non_idempotent = retry_non_idempotent

        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

        if headers:
            default_headers.update(headers)
        self.session.headers.update(default_headers)

        if cookies:
            for name, value in cookies.items():
                self.session.cookies.set(name, value)

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """带重试的请求"""
        kwargs.setdefault("timeout", self.timeout)
        retryable = method.upper() in {"GET", "HEAD", "OPTIONS"} or self.retry_non_idempotent
        attempts = self.max_retries if retryable else 1
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.request(method, url, **kwargs)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == attempts:
                    raise
                time.sleep(self.retry_delay * attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < attempts:
                    try:
                        wait = min(60.0, max(0.0, float(response.headers.get("Retry-After", ""))))
                    except ValueError:
                        wait = self.retry_delay * attempt
                    response.close()
                    time.sleep(wait)
                    continue
            response.raise_for_status()
            return response

    def close(self):
        self.session.close()

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def request_with_delay(
        self, method: str, url: str, delay: float = 1.0, **kwargs
    ) -> requests.Response:
        """带延迟的请求（避免触发频率限制）"""
        jitter = random.uniform(0, delay * 0.3)
        time.sleep(delay + jitter)
        return self.request(method, url, **kwargs)

    def set_cookie(self, name: str, value: str, domain: str = ""):
        """设置 Cookie"""
        self.session.cookies.set(name, value, **({"domain": domain} if domain else {}))

    def update_cookies_from_response(self, response: requests.Response):
        """从响应中更新 Cookie"""
        self.session.cookies.update(response.cookies)

    def get_cookie_string(self) -> str:
        """获取 Cookie 字符串"""
        return "; ".join(f"{c.name}={c.value}" for c in self.session.cookies)


# ====== curl_cffi 版本（对抗 TLS 指纹检测时使用）======
#
# from curl_cffi import requests as curl_requests
#
# class CurlRequestClient:
#     """使用 curl_cffi 的 HTTP 客户端，支持浏览器 TLS 指纹模拟"""
#
#     def __init__(self, impersonate: str = "chrome120"):
#         self.session = curl_requests.Session(impersonate=impersonate)
#
#     def get(self, url: str, **kwargs):
#         return self.session.get(url, **kwargs)
#
#     def post(self, url: str, **kwargs):
#         return self.session.post(url, **kwargs)
