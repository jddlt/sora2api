"""Free proxy pool manager - integrates with proxifly free proxy list"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from curl_cffi.requests import AsyncSession
from ..core.database import Database
from ..core.logger import debug_logger


@dataclass
class ProxyInfo:
    """Proxy information with health tracking"""
    url: str  # Full proxy URL (e.g., http://ip:port)
    protocol: str  # http or socks5
    ip: str
    port: int
    https: bool
    anonymity: str  # transparent, anonymous, elite
    score: float  # Original score from proxifly
    country: str

    # Health tracking
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[float] = None
    last_success: Optional[float] = None
    last_failure: Optional[float] = None
    avg_response_time: float = 0.0
    is_healthy: bool = True

    @property
    def health_score(self) -> float:
        """Calculate health score based on success rate and response time"""
        if self.success_count + self.failure_count == 0:
            return self.score  # Use original score if not tested

        total = self.success_count + self.failure_count
        success_rate = self.success_count / total

        # Penalize slow proxies (normalize response time, lower is better)
        time_penalty = min(1.0, self.avg_response_time / 10.0) * 0.3

        # Combine: 70% success rate + 30% speed factor
        return (success_rate * 0.7 + (1 - time_penalty) * 0.3) * 10


class FreeProxyManager:
    """Manages a pool of free proxies from proxifly"""

    PROXY_LIST_URL = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.json"

    # Refresh interval (how often to fetch new proxy list)
    REFRESH_INTERVAL = 300  # 5 minutes

    # Health check settings
    HEALTH_CHECK_URL = "https://sora.chatgpt.com"
    HEALTH_CHECK_TIMEOUT = 15

    # Proxy filtering
    MIN_SCORE = 0.5  # Minimum proxifly score to consider
    PREFERRED_ANONYMITY = ["anonymous", "elite"]  # Prefer anonymous proxies
    ALLOWED_PROTOCOLS = ["socks5"]  # Only use SOCKS5 proxies (more reliable for OpenAI)

    # Failure threshold before marking proxy unhealthy
    FAILURE_THRESHOLD = 3

    def __init__(self, db: Database):
        self.db = db
        self._proxies: Dict[str, ProxyInfo] = {}  # url -> ProxyInfo
        self._last_refresh: Optional[float] = None
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize the proxy pool by fetching proxies"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            await self._refresh_proxy_list()
            self._initialized = True
            debug_logger.log_info(f"FreeProxyManager initialized with {len(self._proxies)} proxies")

    async def _refresh_proxy_list(self):
        """Fetch fresh proxy list from proxifly"""
        try:
            async with AsyncSession() as session:
                response = await session.get(
                    self.PROXY_LIST_URL,
                    timeout=30,
                    impersonate="chrome"
                )

                if response.status_code != 200:
                    debug_logger.log_info(f"Failed to fetch proxy list: {response.status_code}")
                    return

                proxies_data = response.json()

                # Parse and filter proxies
                new_proxies: Dict[str, ProxyInfo] = {}
                for proxy_data in proxies_data:
                    # Filter by score
                    score = proxy_data.get("score", 0)
                    if score < self.MIN_SCORE:
                        continue

                    # Build proxy URL
                    protocol = proxy_data.get("protocol", "http")
                    ip = proxy_data.get("ip", "")
                    port = proxy_data.get("port", 0)

                    if not ip or not port:
                        continue

                    # Filter by protocol (only SOCKS5)
                    if protocol not in self.ALLOWED_PROTOCOLS:
                        continue

                    proxy_url = f"{protocol}://{ip}:{port}"

                    # Preserve existing health data if proxy was already known
                    if proxy_url in self._proxies:
                        existing = self._proxies[proxy_url]
                        new_proxies[proxy_url] = existing
                        # Update score from new data
                        existing.score = score
                    else:
                        geo = proxy_data.get("geolocation", {})
                        new_proxies[proxy_url] = ProxyInfo(
                            url=proxy_url,
                            protocol=protocol,
                            ip=ip,
                            port=port,
                            https=proxy_data.get("https", False),
                            anonymity=proxy_data.get("anonymity", "unknown"),
                            score=score,
                            country=geo.get("country", "Unknown")
                        )

                self._proxies = new_proxies
                self._last_refresh = time.time()
                debug_logger.log_info(f"Refreshed proxy list: {len(self._proxies)} SOCKS5 proxies available (filtered from {len(proxies_data)} total)")

        except Exception as e:
            debug_logger.log_info(f"Error refreshing proxy list: {e}")

    async def _ensure_fresh_proxies(self):
        """Ensure proxy list is fresh, refresh if needed"""
        if self._last_refresh is None:
            await self._refresh_proxy_list()
            return

        if time.time() - self._last_refresh > self.REFRESH_INTERVAL:
            await self._refresh_proxy_list()

    def _get_healthy_proxies(self) -> List[ProxyInfo]:
        """Get list of healthy proxies sorted by health score"""
        healthy = [p for p in self._proxies.values() if p.is_healthy]
        # Sort by health score (descending) with preference for anonymous proxies
        healthy.sort(key=lambda p: (
            p.anonymity in self.PREFERRED_ANONYMITY,
            p.health_score
        ), reverse=True)
        return healthy

    async def get_best_proxy(self, exclude_urls: Optional[List[str]] = None) -> Optional[str]:
        """Get the best available proxy URL

        Args:
            exclude_urls: List of proxy URLs to exclude (e.g., already tried proxies)

        Returns:
            Proxy URL string or None if no healthy proxies available
        """
        await self._ensure_fresh_proxies()

        exclude_set = set(exclude_urls or [])
        healthy = self._get_healthy_proxies()

        for proxy in healthy:
            if proxy.url not in exclude_set:
                return proxy.url

        # If all healthy proxies are excluded, try any proxy
        for proxy in self._proxies.values():
            if proxy.url not in exclude_set:
                return proxy.url

        return None

    async def bind_proxy_to_token(self, token_id: int, exclude_urls: Optional[List[str]] = None, max_attempts: int = 10) -> Optional[str]:
        """Bind a healthy proxy to a token (verifies proxy works before binding)

        Args:
            token_id: Token ID to bind proxy to
            exclude_urls: Proxy URLs to exclude
            max_attempts: Maximum number of proxies to try before giving up

        Returns:
            The bound proxy URL, or None if no working proxy available
        """
        # Get all tokens to find already-used proxies
        all_tokens = await self.db.get_all_tokens()
        used_proxies = set()
        for token in all_tokens:
            if token.proxy_url and token.id != token_id:
                used_proxies.add(token.proxy_url)

        # Combine with explicitly excluded URLs
        all_excluded = list(used_proxies)
        if exclude_urls:
            all_excluded.extend(exclude_urls)

        # Try multiple proxies until we find one that works
        tried_proxies = set(all_excluded)
        attempts = 0

        while attempts < max_attempts:
            proxy_url = await self.get_best_proxy(list(tried_proxies) if tried_proxies else None)

            if not proxy_url:
                debug_logger.log_info(f"No more proxies available to try for token {token_id}")
                break

            # Add to tried list so we don't try again
            tried_proxies.add(proxy_url)
            attempts += 1

            debug_logger.log_info(f"Testing proxy {proxy_url} for token {token_id} (attempt {attempts}/{max_attempts})")

            # Verify proxy works before binding
            is_working = await self.health_check_proxy(proxy_url)

            if is_working:
                # Proxy works! Bind it to the token
                await self.db.update_token(token_id, proxy_url=proxy_url)
                debug_logger.log_info(f"Successfully bound working proxy {proxy_url} to token {token_id}")
                return proxy_url
            else:
                debug_logger.log_info(f"Proxy {proxy_url} failed health check, trying next...")

        debug_logger.log_info(f"Failed to find working proxy for token {token_id} after {attempts} attempts")
        return None

    def report_success(self, proxy_url: str, response_time: float = 0.0):
        """Report successful use of a proxy

        Args:
            proxy_url: The proxy URL that was used
            response_time: Response time in seconds
        """
        if proxy_url not in self._proxies:
            return

        proxy = self._proxies[proxy_url]
        proxy.success_count += 1
        proxy.last_used = time.time()
        proxy.last_success = time.time()
        proxy.is_healthy = True

        # Update average response time
        if proxy.avg_response_time == 0:
            proxy.avg_response_time = response_time
        else:
            proxy.avg_response_time = (proxy.avg_response_time * 0.7) + (response_time * 0.3)

    def report_failure(self, proxy_url: str):
        """Report failed use of a proxy

        Args:
            proxy_url: The proxy URL that failed
        """
        if proxy_url not in self._proxies:
            return

        proxy = self._proxies[proxy_url]
        proxy.failure_count += 1
        proxy.last_used = time.time()
        proxy.last_failure = time.time()

        # Mark as unhealthy if too many consecutive failures
        recent_failures = sum(1 for p in [proxy] if p.failure_count > 0)
        if proxy.failure_count >= self.FAILURE_THRESHOLD:
            if proxy.success_count == 0 or (proxy.failure_count / (proxy.success_count + proxy.failure_count)) > 0.5:
                proxy.is_healthy = False
                debug_logger.log_info(f"Proxy {proxy_url} marked unhealthy after {proxy.failure_count} failures")

    async def rebind_proxy_on_failure(self, token_id: int, failed_proxy_url: str) -> Optional[str]:
        """Rebind a new proxy after the current one fails

        Args:
            token_id: Token ID to rebind
            failed_proxy_url: The proxy URL that failed

        Returns:
            New proxy URL, or None if no healthy proxy available
        """
        # Report failure for the old proxy
        self.report_failure(failed_proxy_url)

        # Bind a new proxy, excluding the failed one
        return await self.bind_proxy_to_token(token_id, exclude_urls=[failed_proxy_url])

    async def health_check_proxy(self, proxy_url: str) -> bool:
        """Check if a specific proxy is working

        Args:
            proxy_url: Proxy URL to check

        Returns:
            True if proxy is working, False otherwise
        """
        try:
            start_time = time.time()
            async with AsyncSession() as session:
                response = await session.get(
                    self.HEALTH_CHECK_URL,
                    proxy=proxy_url,
                    timeout=self.HEALTH_CHECK_TIMEOUT,
                    impersonate="chrome"
                )

                response_time = time.time() - start_time

                if response.status_code == 200:
                    self.report_success(proxy_url, response_time)
                    return True
                else:
                    self.report_failure(proxy_url)
                    return False

        except Exception as e:
            debug_logger.log_info(f"Health check failed for {proxy_url}: {e}")
            self.report_failure(proxy_url)
            return False

    async def batch_health_check(self, max_concurrent: int = 10) -> Dict[str, bool]:
        """Run health check on all proxies concurrently

        Args:
            max_concurrent: Maximum concurrent health checks

        Returns:
            Dict mapping proxy URL to health status
        """
        await self._ensure_fresh_proxies()

        results: Dict[str, bool] = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def check_with_semaphore(proxy_url: str) -> tuple:
            async with semaphore:
                is_healthy = await self.health_check_proxy(proxy_url)
                return proxy_url, is_healthy

        tasks = [check_with_semaphore(url) for url in self._proxies.keys()]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, tuple):
                url, is_healthy = result
                results[url] = is_healthy

        healthy_count = sum(1 for v in results.values() if v)
        debug_logger.log_info(f"Batch health check: {healthy_count}/{len(results)} proxies healthy")

        return results

    async def find_fastest_working_proxy(self, exclude_urls: Optional[List[str]] = None, max_test: int = 100, max_concurrent: int = 20) -> Optional[tuple]:
        """Find the fastest working proxy by testing multiple proxies concurrently

        Args:
            exclude_urls: Proxy URLs to exclude (already used by other tokens)
            max_test: Maximum number of proxies to test
            max_concurrent: Maximum concurrent tests

        Returns:
            Tuple of (proxy_url, response_time) or None if no working proxy found
        """
        await self._ensure_fresh_proxies()

        exclude_set = set(exclude_urls or [])

        # Get proxies to test (excluding already used ones)
        proxies_to_test = [
            p.url for p in self._get_healthy_proxies()
            if p.url not in exclude_set
        ][:max_test]

        if not proxies_to_test:
            debug_logger.log_info("No proxies available to test")
            return None

        debug_logger.log_info(f"Testing {len(proxies_to_test)} proxies to find fastest...")

        results: List[tuple] = []  # (proxy_url, response_time)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def test_proxy(proxy_url: str) -> Optional[tuple]:
            async with semaphore:
                try:
                    start_time = time.time()
                    async with AsyncSession() as session:
                        response = await session.get(
                            self.HEALTH_CHECK_URL,
                            proxy=proxy_url,
                            timeout=self.HEALTH_CHECK_TIMEOUT,
                            impersonate="chrome"
                        )
                        response_time = time.time() - start_time

                        if response.status_code == 200:
                            self.report_success(proxy_url, response_time)
                            debug_logger.log_info(f"Proxy {proxy_url} works, response time: {response_time:.2f}s")
                            return (proxy_url, response_time)
                        else:
                            self.report_failure(proxy_url)
                            return None
                except Exception as e:
                    self.report_failure(proxy_url)
                    return None

        tasks = [test_proxy(url) for url in proxies_to_test]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, tuple) and result is not None:
                results.append(result)

        if not results:
            debug_logger.log_info("No working proxies found")
            return None

        # Sort by response time (fastest first)
        results.sort(key=lambda x: x[1])
        fastest = results[0]
        debug_logger.log_info(f"Found {len(results)} working proxies, fastest: {fastest[0]} ({fastest[1]:.2f}s)")

        return fastest

    async def bind_fastest_proxy_to_token(self, token_id: int) -> Optional[dict]:
        """Find and bind the fastest working proxy to a token

        Args:
            token_id: Token ID to bind proxy to

        Returns:
            Dict with proxy_url, response_time, tested_count, working_count or None
        """
        # Get all tokens to find already-used proxies
        all_tokens = await self.db.get_all_tokens()
        used_proxies = [t.proxy_url for t in all_tokens if t.proxy_url and t.id != token_id]

        result = await self.find_fastest_working_proxy(exclude_urls=used_proxies, max_test=100, max_concurrent=20)

        if result:
            proxy_url, response_time = result
            await self.db.update_token(token_id, proxy_url=proxy_url)
            debug_logger.log_info(f"Bound fastest proxy {proxy_url} ({response_time:.2f}s) to token {token_id}")
            return {
                "proxy_url": proxy_url,
                "response_time": round(response_time, 2)
            }

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get proxy pool statistics

        Returns:
            Dict with pool statistics
        """
        total = len(self._proxies)
        healthy = sum(1 for p in self._proxies.values() if p.is_healthy)

        by_country: Dict[str, int] = {}
        by_anonymity: Dict[str, int] = {}

        for proxy in self._proxies.values():
            by_country[proxy.country] = by_country.get(proxy.country, 0) + 1
            by_anonymity[proxy.anonymity] = by_anonymity.get(proxy.anonymity, 0) + 1

        return {
            "total_proxies": total,
            "healthy_proxies": healthy,
            "unhealthy_proxies": total - healthy,
            "last_refresh": datetime.fromtimestamp(self._last_refresh).isoformat() if self._last_refresh else None,
            "by_country": by_country,
            "by_anonymity": by_anonymity
        }

    def get_proxy_list(self) -> List[Dict[str, Any]]:
        """Get list of all proxies with their info

        Returns:
            List of proxy info dicts
        """
        return [
            {
                "url": p.url,
                "protocol": p.protocol,
                "ip": p.ip,
                "port": p.port,
                "https": p.https,
                "anonymity": p.anonymity,
                "country": p.country,
                "score": p.score,
                "health_score": p.health_score,
                "is_healthy": p.is_healthy,
                "success_count": p.success_count,
                "failure_count": p.failure_count,
                "avg_response_time": round(p.avg_response_time, 2)
            }
            for p in sorted(self._proxies.values(), key=lambda x: x.health_score, reverse=True)
        ]
