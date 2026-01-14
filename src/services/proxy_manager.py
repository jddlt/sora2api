"""Proxy management module"""
from typing import Optional, TYPE_CHECKING, Tuple
from ..core.database import Database
from ..core.models import ProxyConfig
from ..core.logger import debug_logger

if TYPE_CHECKING:
    from .free_proxy_manager import FreeProxyManager


class ProxyManager:
    """Proxy configuration manager with free proxy pool support"""

    def __init__(self, db: Database):
        self.db = db
        self._free_proxy_manager: Optional["FreeProxyManager"] = None
        self._free_proxy_enabled: bool = False

    def set_free_proxy_manager(self, manager: "FreeProxyManager", enabled: bool = True):
        """Set the free proxy manager instance

        Args:
            manager: FreeProxyManager instance
            enabled: Whether to enable auto-binding from free proxy pool
        """
        self._free_proxy_manager = manager
        self._free_proxy_enabled = enabled

    async def get_proxy_url(self, token_id: Optional[int] = None, proxy_url: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """Get proxy URL for a token, with fallback to global proxy

        Priority order:
        1. Direct proxy_url parameter
        2. Token-specific proxy_url from database
        3. Free proxy pool (if enabled, auto-binds to token)
        4. Global proxy (if enabled) - as fallback

        Args:
            token_id: Token ID (optional). If provided, returns token-specific proxy if set,
                     otherwise falls back to free proxy pool or global proxy.
            proxy_url: Direct proxy URL (optional). If provided, returns this proxy URL directly.

        Returns:
            Tuple of (proxy_url, bind_action) where bind_action describes what happened:
            - None: no binding occurred
            - "bound": new proxy was bound from free pool
            - "global": using global proxy as fallback
        """
        # If proxy_url is directly provided, use it
        if proxy_url:
            return proxy_url, None

        # If token_id is provided, try to get token-specific proxy first
        if token_id is not None:
            token = await self.db.get_token(token_id)
            if token and token.proxy_url:
                return token.proxy_url, None

            # Token has no proxy - try to bind from free proxy pool first
            if self._free_proxy_enabled and self._free_proxy_manager and token:
                await self._free_proxy_manager.initialize()
                new_proxy = await self._free_proxy_manager.bind_proxy_to_token(token_id)
                if new_proxy:
                    debug_logger.log_info(f"Auto-bound free proxy {new_proxy} to token {token_id} (email: {token.email})")
                    return new_proxy, "bound"

        # Fall back to global proxy (as fallback/兜底)
        config = await self.db.get_proxy_config()
        if config.proxy_enabled and config.proxy_url:
            return config.proxy_url, "global"

        return None, None

    async def report_proxy_success(self, token_id: Optional[int], response_time: float = 0.0):
        """Report successful proxy use for health tracking

        Args:
            token_id: Token ID that used the proxy
            response_time: Response time in seconds
        """
        if not self._free_proxy_manager or not token_id:
            return

        token = await self.db.get_token(token_id)
        if token and token.proxy_url:
            self._free_proxy_manager.report_success(token.proxy_url, response_time)

    async def report_proxy_failure(self, token_id: Optional[int]) -> Optional[str]:
        """Report failed proxy use and optionally rebind a new proxy

        Args:
            token_id: Token ID whose proxy failed

        Returns:
            New proxy URL if rebind was successful, None otherwise
        """
        if not self._free_proxy_manager or not token_id:
            return None

        token = await self.db.get_token(token_id)
        if not token or not token.proxy_url:
            return None

        # Only handle proxies that came from the free pool
        if token.proxy_url in [p.url for p in self._free_proxy_manager._proxies.values()]:
            new_proxy = await self._free_proxy_manager.rebind_proxy_on_failure(token_id, token.proxy_url)
            return new_proxy

        return None

    async def update_proxy_config(self, enabled: bool, proxy_url: Optional[str]):
        """Update proxy configuration"""
        await self.db.update_proxy_config(enabled, proxy_url)

    async def get_proxy_config(self) -> ProxyConfig:
        """Get proxy configuration"""
        return await self.db.get_proxy_config()

    @property
    def free_proxy_manager(self) -> Optional["FreeProxyManager"]:
        """Get the free proxy manager instance"""
        return self._free_proxy_manager

    @property
    def free_proxy_enabled(self) -> bool:
        """Check if free proxy pool is enabled"""
        return self._free_proxy_enabled
