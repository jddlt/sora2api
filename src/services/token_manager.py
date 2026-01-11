"""Token management module"""
import jwt
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from curl_cffi.requests import AsyncSession
from faker import Faker
from ..core.database import Database
from ..core.models import Token, TokenStats
from ..core.config import config
from .proxy_manager import ProxyManager
from ..core.logger import debug_logger

class TokenManager:
    """Token lifecycle manager"""

    def __init__(self, db: Database):
        self.db = db
        self._lock = asyncio.Lock()
        self.proxy_manager = ProxyManager(db)
        self.fake = Faker()
    
    async def decode_jwt(self, token: str) -> dict:
        """Decode JWT token without verification"""
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded
        except Exception as e:
            raise ValueError(f"Invalid JWT token: {str(e)}")

    def _generate_random_username(self) -> str:
        """Generate a random username using faker

        Returns:
            A random username string
        """
        # 生成真实姓名
        first_name = self.fake.first_name()
        last_name = self.fake.last_name()

        # 去除姓名中的空格和特殊字符，只保留字母
        first_name_clean = ''.join(c for c in first_name if c.isalpha())
        last_name_clean = ''.join(c for c in last_name if c.isalpha())

        # 生成1-4位随机数字
        random_digits = str(random.randint(1, 9999))

        # 随机选择用户名格式
        format_choice = random.choice([
            f"{first_name_clean}{last_name_clean}{random_digits}",
            f"{first_name_clean}.{last_name_clean}{random_digits}",
            f"{first_name_clean}{random_digits}",
            f"{last_name_clean}{random_digits}",
            f"{first_name_clean[0]}{last_name_clean}{random_digits}",
            f"{first_name_clean}{last_name_clean[0]}{random_digits}"
        ])

        # 转换为小写
        return format_choice.lower()

    async def get_user_info(self, access_token: str, token_id: Optional[int] = None, proxy_url: Optional[str] = None) -> dict:
        """Get user info from Sora API"""
        proxy_url = await self.proxy_manager.get_proxy_url(token_id, proxy_url)

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Origin": "https://sora.chatgpt.com",
                "Pragma": "no-cache",
                "Priority": "u=1, i",
                "Referer": "https://sora.chatgpt.com/",
                "Sec-Ch-Ua": '"Not_A Brand"; v="8", "Chromium"; v="120", "Safari"; v="17"',
                "Sec-Ch-Ua-Mobile": "?1",
                "Sec-Ch-Ua-Platform": '"iOS"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "safari_ios"  # 模拟 iOS Safari 浏览器指纹
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.get(
                f"{config.sora_base_url}/me",
                **kwargs
            )

            if response.status_code != 200:
                # Check for token_invalidated error
                if response.status_code == 401:
                    try:
                        error_data = response.json()
                        error_code = error_data.get("error", {}).get("code", "")
                        if error_code == "token_invalidated":
                            raise ValueError(f"401 token_invalidated: Token has been invalidated")
                    except (ValueError, KeyError):
                        pass
                raise ValueError(f"Failed to get user info: {response.status_code}")

            data = response.json()
            print(f"\n{'='*60}")
            print(f"📋 [/me] 完整响应:")
            import json
            print(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"{'='*60}\n")
            return data

    async def get_subscription_info(self, token: str, token_id: Optional[int] = None, proxy_url: Optional[str] = None) -> Dict[str, Any]:
        """Get subscription information from Sora API

        Returns:
            {
                "plan_type": "chatgpt_team",
                "plan_title": "ChatGPT Business",
                "subscription_end": "2025-11-13T16:58:21Z"
            }
        """
        print(f"🔍 开始获取订阅信息...")
        proxy_url = await self.proxy_manager.get_proxy_url(token_id, proxy_url)

        headers = {
            "Authorization": f"Bearer {token}"
        }

        async with AsyncSession() as session:
            url = "https://sora.chatgpt.com/backend/billing/subscriptions"
            print(f"📡 请求 URL: {url}")
            print(f"🔑 使用 Token: {token[:30]}...")

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "safari_ios"  # 模拟 iOS Safari 浏览器指纹
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 使用代理: {proxy_url}")

            response = await session.get(url, **kwargs)
            print(f"📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"📦 响应数据: {data}")

                # 提取第一个订阅信息
                if data.get("data") and len(data["data"]) > 0:
                    subscription = data["data"][0]
                    plan = subscription.get("plan", {})

                    result = {
                        "plan_type": plan.get("id", ""),
                        "plan_title": plan.get("title", ""),
                        "subscription_end": subscription.get("end_ts", "")
                    }
                    print(f"✅ 订阅信息提取成功: {result}")
                    return result

                print(f"⚠️  响应数据中没有订阅信息")
                return {
                    "plan_type": "",
                    "plan_title": "",
                    "subscription_end": ""
                }
            else:
                print(f"❌ Failed to get subscription info: {response.status_code}")
                print(f"📄 响应内容: {response.text}")

                # Check for token_expired error
                try:
                    error_data = response.json()
                    error_info = error_data.get("error", {})
                    if error_info.get("code") == "token_expired":
                        raise Exception(f"Token已过期: {error_info.get('message', 'Token expired')}")
                except ValueError:
                    pass

                raise Exception(f"Failed to get subscription info: {response.status_code}")

    async def get_sora2_invite_code(self, access_token: str, token_id: Optional[int] = None, proxy_url: Optional[str] = None) -> dict:
        """Get Sora2 invite code"""
        proxy_url = await self.proxy_manager.get_proxy_url(token_id, proxy_url)

        print(f"🔍 开始获取Sora2邀请码...")

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Origin": "https://sora.chatgpt.com",
                "Pragma": "no-cache",
                "Priority": "u=1, i",
                "Referer": "https://sora.chatgpt.com/",
                "Sec-Ch-Ua": '"Not_A Brand"; v="8", "Chromium"; v="120", "Safari"; v="17"',
                "Sec-Ch-Ua-Mobile": "?1",
                "Sec-Ch-Ua-Platform": '"iOS"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "safari_ios"  # 模拟 iOS Safari 浏览器指纹
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 使用代理: {proxy_url}")

            response = await session.get(
                "https://sora.chatgpt.com/backend/project_y/invite/mine",
                **kwargs
            )

            print(f"📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Sora2邀请码获取成功: {data}")
                return {
                    "supported": True,
                    "invite_code": data.get("invite_code"),
                    "redeemed_count": data.get("redeemed_count", 0),
                    "total_count": data.get("total_count", 0)
                }
            else:
                print(f"❌ 获取Sora2邀请码失败: {response.status_code}")
                print(f"📄 响应内容: {response.text}")

                # Check for specific errors
                try:
                    error_data = response.json()
                    error_info = error_data.get("error", {})

                    # Check for unsupported_country_code
                    if error_info.get("code") == "unsupported_country_code":
                        country = error_info.get("param", "未知")
                        raise Exception(f"Sora在您的国家/地区不可用 ({country}): {error_info.get('message', '')}")

                    # Check if it's 401 unauthorized (token doesn't support Sora2)
                    if response.status_code == 401 and "Unauthorized" in error_info.get("message", ""):
                        print(f"⚠️  Token不支持Sora2，尝试激活...")

                        # Try to activate Sora2
                        try:
                            activate_response = await session.get(
                                "https://sora.chatgpt.com/backend/m/bootstrap",
                                **kwargs
                            )

                            if activate_response.status_code == 200:
                                print(f"✅ Sora2激活请求成功，重新获取邀请码...")

                                # Retry getting invite code
                                retry_response = await session.get(
                                    "https://sora.chatgpt.com/backend/project_y/invite/mine",
                                    **kwargs
                                )

                                if retry_response.status_code == 200:
                                    retry_data = retry_response.json()
                                    print(f"✅ Sora2激活成功！邀请码: {retry_data}")
                                    return {
                                        "supported": True,
                                        "invite_code": retry_data.get("invite_code"),
                                        "redeemed_count": retry_data.get("redeemed_count", 0),
                                        "total_count": retry_data.get("total_count", 0)
                                    }
                                else:
                                    print(f"⚠️  激活后仍无法获取邀请码: {retry_response.status_code}")
                            else:
                                print(f"⚠️  Sora2激活失败: {activate_response.status_code}")
                        except Exception as activate_e:
                            print(f"⚠️  Sora2激活过程出错: {activate_e}")

                        return {
                            "supported": False,
                            "invite_code": None
                        }
                except ValueError:
                    pass

                return {
                    "supported": False,
                    "invite_code": None
                }

    async def get_sora2_remaining_count(self, access_token: str, token_id: Optional[int] = None, proxy_url: Optional[str] = None) -> dict:
        """Get Sora2 remaining video count

        Returns:
            {
                "remaining_count": 27,
                "rate_limit_reached": false,
                "access_resets_in_seconds": 46833
            }
        """
        proxy_url = await self.proxy_manager.get_proxy_url(token_id, proxy_url)

        print(f"🔍 开始获取Sora2剩余次数...")

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Origin": "https://sora.chatgpt.com",
                "Pragma": "no-cache",
                "Priority": "u=1, i",
                "Referer": "https://sora.chatgpt.com/",
                "Sec-Ch-Ua": '"Not_A Brand"; v="8", "Chromium"; v="120", "Safari"; v="17"',
                "Sec-Ch-Ua-Mobile": "?1",
                "Sec-Ch-Ua-Platform": '"iOS"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "safari_ios"  # 模拟 iOS Safari 浏览器指纹
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 使用代理: {proxy_url}")

            response = await session.get(
                "https://sora.chatgpt.com/backend/nf/check",
                **kwargs
            )

            print(f"📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Sora2剩余次数获取成功: {data}")

                rate_limit_info = data.get("rate_limit_and_credit_balance", {})
                return {
                    "success": True,
                    "remaining_count": rate_limit_info.get("estimated_num_videos_remaining", 0),
                    "rate_limit_reached": rate_limit_info.get("rate_limit_reached", False),
                    "access_resets_in_seconds": rate_limit_info.get("access_resets_in_seconds", 0)
                }
            else:
                print(f"❌ 获取Sora2剩余次数失败: {response.status_code}")
                print(f"📄 响应内容: {response.text[:500]}")
                return {
                    "success": False,
                    "remaining_count": 0,
                    "error": f"Failed to get remaining count: {response.status_code}"
                }

    async def check_username_available(self, access_token: str, username: str) -> bool:
        """Check if username is available

        Args:
            access_token: Access token for authentication
            username: Username to check

        Returns:
            True if username is available, False otherwise
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        print(f"🔍 检查用户名是否可用: {username}")

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            kwargs = {
                "headers": headers,
                "json": {"username": username},
                "timeout": 30,
                "impersonate": "safari_ios"
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 使用代理: {proxy_url}")

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/profile/username/check",
                **kwargs
            )

            print(f"📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                available = data.get("available", False)
                print(f"✅ 用户名检查结果: available={available}")
                return available
            else:
                print(f"❌ 用户名检查失败: {response.status_code}")
                print(f"📄 响应内容: {response.text[:500]}")
                return False

    async def set_username(self, access_token: str, username: str) -> dict:
        """Set username for the account

        Args:
            access_token: Access token for authentication
            username: Username to set

        Returns:
            User profile information after setting username
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        print(f"🔍 开始设置用户名: {username}")

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            kwargs = {
                "headers": headers,
                "json": {"username": username},
                "timeout": 30,
                "impersonate": "safari_ios"
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 使用代理: {proxy_url}")

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/profile/username/set",
                **kwargs
            )

            print(f"📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ 用户名设置成功: {data.get('username')}")
                return data
            else:
                print(f"❌ 用户名设置失败: {response.status_code}")
                print(f"📄 响应内容: {response.text[:500]}")
                raise Exception(f"Failed to set username: {response.status_code}")

    async def activate_sora2_invite(self, access_token: str, invite_code: str) -> dict:
        """Activate Sora2 with invite code"""
        import uuid
        proxy_url = await self.proxy_manager.get_proxy_url()

        print(f"🔍 开始激活Sora2邀请码: {invite_code}")
        print(f"🔑 Access Token 前缀: {access_token[:50]}...")

        async with AsyncSession() as session:
            # 生成设备ID
            device_id = str(uuid.uuid4())

            # 只设置必要的头，让 impersonate 处理其他
            headers = {
                "authorization": f"Bearer {access_token}",
                "cookie": f"oai-did={device_id}"
            }

            print(f"🆔 设备ID: {device_id}")
            print(f"📦 请求体: {{'invite_code': '{invite_code}'}}")

            kwargs = {
                "headers": headers,
                "json": {"invite_code": invite_code},
                "timeout": 30,
                "impersonate": "safari_ios"  # 模拟 iOS Safari 浏览器指纹
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 使用代理: {proxy_url}")

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/invite/accept",
                **kwargs
            )

            print(f"📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Sora2激活成功: {data}")
                return {
                    "success": data.get("success", False),
                    "already_accepted": data.get("already_accepted", False)
                }
            else:
                print(f"❌ Sora2激活失败: {response.status_code}")
                print(f"📄 响应内容: {response.text[:500]}")
                raise Exception(f"Failed to activate Sora2: {response.status_code}")

    async def st_to_at(self, session_token: str, proxy_url: Optional[str] = None) -> dict:
        """Convert Session Token to Access Token"""
        debug_logger.log_info(f"[ST_TO_AT] 开始转换 Session Token 为 Access Token...")
        proxy_url = await self.proxy_manager.get_proxy_url(proxy_url=proxy_url)

        async with AsyncSession() as session:
            headers = {
                "Cookie": f"__Secure-next-auth.session-token={session_token}",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Origin": "https://sora.chatgpt.com",
                "Pragma": "no-cache",
                "Priority": "u=1, i",
                "Referer": "https://sora.chatgpt.com/",
                "Sec-Ch-Ua": '"Not_A Brand"; v="8", "Chromium"; v="120", "Safari"; v="17"',
                "Sec-Ch-Ua-Mobile": "?1",
                "Sec-Ch-Ua-Platform": '"iOS"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "safari_ios"  # 模拟 iOS Safari 浏览器指纹
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                debug_logger.log_info(f"[ST_TO_AT] 使用代理: {proxy_url}")

            url = "https://sora.chatgpt.com/api/auth/session"
            debug_logger.log_info(f"[ST_TO_AT] 📡 请求 URL: {url}")

            try:
                response = await session.get(url, **kwargs)
                debug_logger.log_info(f"[ST_TO_AT] 📥 响应状态码: {response.status_code}")

                if response.status_code != 200:
                    error_msg = f"Failed to convert ST to AT: {response.status_code}"
                    debug_logger.log_info(f"[ST_TO_AT] ❌ {error_msg}")
                    debug_logger.log_info(f"[ST_TO_AT] 响应内容: {response.text[:500]}")
                    raise ValueError(error_msg)

                # 获取响应文本用于调试
                response_text = response.text
                debug_logger.log_info(f"[ST_TO_AT] 📄 响应内容: {response_text[:500]}")

                # 检查响应是否为空
                if not response_text or response_text.strip() == "":
                    debug_logger.log_info(f"[ST_TO_AT] ❌ 响应体为空")
                    raise ValueError("Response body is empty")

                try:
                    data = response.json()
                except Exception as json_err:
                    debug_logger.log_info(f"[ST_TO_AT] ❌ JSON解析失败: {str(json_err)}")
                    debug_logger.log_info(f"[ST_TO_AT] 原始响应: {response_text[:1000]}")
                    raise ValueError(f"Failed to parse JSON response: {str(json_err)}")

                # 检查data是否为None
                if data is None:
                    debug_logger.log_info(f"[ST_TO_AT] ❌ 响应JSON为空")
                    raise ValueError("Response JSON is empty")

                access_token = data.get("accessToken")
                email = data.get("user", {}).get("email") if data.get("user") else None
                expires = data.get("expires")

                # 检查必要字段
                if not access_token:
                    debug_logger.log_info(f"[ST_TO_AT] ❌ 响应中缺少 accessToken 字段")
                    debug_logger.log_info(f"[ST_TO_AT] 响应数据: {data}")
                    raise ValueError("Missing accessToken in response")

                debug_logger.log_info(f"[ST_TO_AT] ✅ ST 转换成功")
                debug_logger.log_info(f"  - Email: {email}")
                debug_logger.log_info(f"  - 过期时间: {expires}")

                return {
                    "access_token": access_token,
                    "email": email,
                    "expires": expires
                }
            except Exception as e:
                debug_logger.log_info(f"[ST_TO_AT] 🔴 异常: {str(e)}")
                raise
    
    async def rt_to_at(self, refresh_token: str, client_id: Optional[str] = None, proxy_url: Optional[str] = None) -> dict:
        """Convert Refresh Token to Access Token

        Args:
            refresh_token: Refresh Token
            client_id: Client ID (optional, uses default if not provided)
            proxy_url: Proxy URL (optional, uses global proxy if not provided)
        """
        # Use provided client_id or default
        effective_client_id = client_id or "app_LlGpXReQgckcGGUo2JrYvtJK"

        debug_logger.log_info(f"[RT_TO_AT] 开始转换 Refresh Token 为 Access Token...")
        debug_logger.log_info(f"[RT_TO_AT] 使用 Client ID: {effective_client_id[:20]}...")
        proxy_url = await self.proxy_manager.get_proxy_url(proxy_url=proxy_url)

        async with AsyncSession() as session:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }

            kwargs = {
                "headers": headers,
                "json": {
                    "client_id": effective_client_id,
                    "grant_type": "refresh_token",
                    "redirect_uri": "com.openai.chat://auth0.openai.com/ios/com.openai.chat/callback",
                    "refresh_token": refresh_token
                },
                "timeout": 30,
                "impersonate": "safari_ios"  # 模拟 iOS Safari 浏览器指纹
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                debug_logger.log_info(f"[RT_TO_AT] 使用代理: {proxy_url}")

            url = "https://auth.openai.com/oauth/token"
            debug_logger.log_info(f"[RT_TO_AT] 📡 请求 URL: {url}")

            try:
                response = await session.post(url, **kwargs)
                debug_logger.log_info(f"[RT_TO_AT] 📥 响应状态码: {response.status_code}")

                if response.status_code != 200:
                    error_msg = f"Failed to convert RT to AT: {response.status_code}"
                    debug_logger.log_info(f"[RT_TO_AT] ❌ {error_msg}")
                    debug_logger.log_info(f"[RT_TO_AT] 响应内容: {response.text[:500]}")
                    raise ValueError(f"{error_msg} - {response.text}")

                # 获取响应文本用于调试
                response_text = response.text
                debug_logger.log_info(f"[RT_TO_AT] 📄 响应内容: {response_text[:500]}")

                # 检查响应是否为空
                if not response_text or response_text.strip() == "":
                    debug_logger.log_info(f"[RT_TO_AT] ❌ 响应体为空")
                    raise ValueError("Response body is empty")

                try:
                    data = response.json()
                except Exception as json_err:
                    debug_logger.log_info(f"[RT_TO_AT] ❌ JSON解析失败: {str(json_err)}")
                    debug_logger.log_info(f"[RT_TO_AT] 原始响应: {response_text[:1000]}")
                    raise ValueError(f"Failed to parse JSON response: {str(json_err)}")

                # 检查data是否为None
                if data is None:
                    debug_logger.log_info(f"[RT_TO_AT] ❌ 响应JSON为空")
                    raise ValueError("Response JSON is empty")

                access_token = data.get("access_token")
                new_refresh_token = data.get("refresh_token")
                expires_in = data.get("expires_in")

                # 检查必要字段
                if not access_token:
                    debug_logger.log_info(f"[RT_TO_AT] ❌ 响应中缺少 access_token 字段")
                    debug_logger.log_info(f"[RT_TO_AT] 响应数据: {data}")
                    raise ValueError("Missing access_token in response")

                debug_logger.log_info(f"[RT_TO_AT] ✅ RT 转换成功")
                debug_logger.log_info(f"  - 新 Access Token 有效期: {expires_in} 秒")
                debug_logger.log_info(f"  - Refresh Token 已更新: {'是' if new_refresh_token else '否'}")

                return {
                    "access_token": access_token,
                    "refresh_token": new_refresh_token,
                    "expires_in": expires_in
                }
            except Exception as e:
                debug_logger.log_info(f"[RT_TO_AT] 🔴 异常: {str(e)}")
                raise
    
    async def add_token(self, token_value: str,
                       password: Optional[str] = None,
                       st: Optional[str] = None,
                       rt: Optional[str] = None,
                       client_id: Optional[str] = None,
                       proxy_url: Optional[str] = None,
                       remark: Optional[str] = None,
                       update_if_exists: bool = False,
                       image_enabled: bool = True,
                       video_enabled: bool = True,
                       image_concurrency: int = -1,
                       video_concurrency: int = -1,
                       skip_status_update: bool = False,
                       email: Optional[str] = None) -> Token:
        """Add a new Access Token to database

        Args:
            token_value: Access Token
            password: Account password (optional)
            st: Session Token (optional)
            rt: Refresh Token (optional)
            client_id: Client ID (optional)
            proxy_url: Proxy URL (optional)
            remark: Remark (optional)
            update_if_exists: If True, update existing token instead of raising error
            image_enabled: Enable image generation (default: True)
            video_enabled: Enable video generation (default: True)
            image_concurrency: Image concurrency limit (-1 for no limit)
            video_concurrency: Video concurrency limit (-1 for no limit)

        Returns:
            Token object

        Raises:
            ValueError: If token already exists and update_if_exists is False
        """
        # Check if token already exists
        existing_token = await self.db.get_token_by_value(token_value)
        if existing_token:
            if not update_if_exists:
                raise ValueError(f"Token 已存在（邮箱: {existing_token.email}）。如需更新，请先删除旧 Token 或使用更新功能。")
            # Update existing token
            return await self.update_existing_token(existing_token.id, token_value, st, rt, remark)

        # Decode JWT to get expiry time and email
        decoded = await self.decode_jwt(token_value)

        # Extract expiry time from JWT
        expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None

        # Extract email from JWT (OpenAI JWT format)
        jwt_email = None
        if "https://api.openai.com/profile" in decoded:
            jwt_email = decoded["https://api.openai.com/profile"].get("email")

        # Initialize variables
        name = ""
        plan_type = None
        plan_title = None
        subscription_end = None
        sora2_supported = None
        sora2_invite_code = None
        sora2_redeemed_count = -1
        sora2_total_count = -1
        sora2_remaining_count = -1

        if skip_status_update:
            # Offline mode: use provided email or JWT email, skip API calls
            email = email or jwt_email or ""
            name = email.split("@")[0] if email else ""
        else:
            # Normal mode: get user info from Sora API
            try:
                user_info = await self.get_user_info(token_value, proxy_url=proxy_url)
                email = user_info.get("email", jwt_email or "")
                name = user_info.get("name") or ""
            except Exception as e:
                # If API call fails, use JWT data
                email = jwt_email or ""
                name = email.split("@")[0] if email else ""

            # Get subscription info from Sora API
            try:
                sub_info = await self.get_subscription_info(token_value, proxy_url=proxy_url)
                plan_type = sub_info.get("plan_type")
                plan_title = sub_info.get("plan_title")
                # Parse subscription end time
                if sub_info.get("subscription_end"):
                    from dateutil import parser
                    subscription_end = parser.parse(sub_info["subscription_end"])
            except Exception as e:
                error_msg = str(e)
                # Re-raise if it's a critical error (token expired)
                if "Token已过期" in error_msg:
                    raise
                # If API call fails, subscription info will be None
                print(f"Failed to get subscription info: {e}")

            # Get Sora2 invite code
            sora2_redeemed_count = 0
            sora2_total_count = 0
            sora2_remaining_count = 0
            try:
                sora2_info = await self.get_sora2_invite_code(token_value, proxy_url=proxy_url)
                sora2_supported = sora2_info.get("supported", False)
                sora2_invite_code = sora2_info.get("invite_code")
                sora2_redeemed_count = sora2_info.get("redeemed_count", 0)
                sora2_total_count = sora2_info.get("total_count", 0)

                # If Sora2 is supported, get remaining count
                if sora2_supported:
                    try:
                        remaining_info = await self.get_sora2_remaining_count(token_value, proxy_url=proxy_url)
                        if remaining_info.get("success"):
                            sora2_remaining_count = remaining_info.get("remaining_count", 0)
                            print(f"✅ Sora2剩余次数: {sora2_remaining_count}")
                    except Exception as e:
                        print(f"Failed to get Sora2 remaining count: {e}")
            except Exception as e:
                error_msg = str(e)
                # Re-raise if it's a critical error (unsupported country)
                if "Sora在您的国家/地区不可用" in error_msg:
                    raise
                # If API call fails, Sora2 info will be None
                print(f"Failed to get Sora2 info: {e}")

            # Check and set username if needed
            try:
                # Get fresh user info to check username
                user_info = await self.get_user_info(token_value, proxy_url=proxy_url)
                username = user_info.get("username")

                # If username is null, need to set one
                if username is None:
                    print(f"⚠️  检测到用户名为null，需要设置用户名")

                    # Generate random username
                    max_attempts = 5
                    for attempt in range(max_attempts):
                        generated_username = self._generate_random_username()
                        print(f"🔄 尝试用户名 ({attempt + 1}/{max_attempts}): {generated_username}")

                        # Check if username is available
                        if await self.check_username_available(token_value, generated_username):
                            # Set the username
                            try:
                                await self.set_username(token_value, generated_username)
                                print(f"✅ 用户名设置成功: {generated_username}")
                                break
                            except Exception as e:
                                print(f"❌ 用户名设置失败: {e}")
                                if attempt == max_attempts - 1:
                                    print(f"⚠️  达到最大尝试次数，跳过用户名设置")
                        else:
                            print(f"⚠️  用户名 {generated_username} 已被占用，尝试下一个")
                            if attempt == max_attempts - 1:
                                print(f"⚠️  达到最大尝试次数，跳过用户名设置")
                else:
                    print(f"✅ 用户名已设置: {username}")
            except Exception as e:
                print(f"⚠️  用户名检查/设置过程中出错: {e}")

        # Create token object
        token = Token(
            token=token_value,
            email=email,
            password=password,
            name=name,
            st=st,
            rt=rt,
            client_id=client_id,
            proxy_url=proxy_url,
            remark=remark,
            expiry_time=expiry_time,
            is_active=True,
            plan_type=plan_type,
            plan_title=plan_title,
            subscription_end=subscription_end,
            sora2_supported=sora2_supported,
            sora2_invite_code=sora2_invite_code,
            sora2_redeemed_count=sora2_redeemed_count,
            sora2_total_count=sora2_total_count,
            sora2_remaining_count=sora2_remaining_count,
            image_enabled=image_enabled,
            video_enabled=video_enabled,
            image_concurrency=image_concurrency,
            video_concurrency=video_concurrency
        )

        # Save to database
        token_id = await self.db.add_token(token)
        token.id = token_id

        return token

    async def update_existing_token(self, token_id: int, token_value: str,
                                    st: Optional[str] = None,
                                    rt: Optional[str] = None,
                                    remark: Optional[str] = None) -> Token:
        """Update an existing token with new information"""
        # Decode JWT to get expiry time
        decoded = await self.decode_jwt(token_value)
        expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None

        # Get user info from Sora API
        jwt_email = None
        if "https://api.openai.com/profile" in decoded:
            jwt_email = decoded["https://api.openai.com/profile"].get("email")

        try:
            user_info = await self.get_user_info(token_value)
            email = user_info.get("email", jwt_email or "")
            name = user_info.get("name", "")
        except Exception as e:
            email = jwt_email or ""
            name = email.split("@")[0] if email else ""

        # Get subscription info from Sora API
        plan_type = None
        plan_title = None
        subscription_end = None
        try:
            sub_info = await self.get_subscription_info(token_value)
            plan_type = sub_info.get("plan_type")
            plan_title = sub_info.get("plan_title")
            if sub_info.get("subscription_end"):
                from dateutil import parser
                subscription_end = parser.parse(sub_info["subscription_end"])
        except Exception as e:
            print(f"Failed to get subscription info: {e}")

        # Update token in database
        await self.db.update_token(
            token_id=token_id,
            token=token_value,
            st=st,
            rt=rt,
            remark=remark,
            expiry_time=expiry_time,
            plan_type=plan_type,
            plan_title=plan_title,
            subscription_end=subscription_end
        )

        # Get updated token
        updated_token = await self.db.get_token(token_id)
        return updated_token

    async def delete_token(self, token_id: int):
        """Delete a token"""
        await self.db.delete_token(token_id)

    async def update_token(self, token_id: int,
                          token: Optional[str] = None,
                          password: Optional[str] = None,
                          st: Optional[str] = None,
                          rt: Optional[str] = None,
                          client_id: Optional[str] = None,
                          proxy_url: Optional[str] = None,
                          remark: Optional[str] = None,
                          image_enabled: Optional[bool] = None,
                          video_enabled: Optional[bool] = None,
                          image_concurrency: Optional[int] = None,
                          video_concurrency: Optional[int] = None,
                          skip_status_update: bool = False):
        """Update token (AT, password, ST, RT, client_id, proxy_url, remark, image_enabled, video_enabled, concurrency limits)"""
        # If token (AT) is updated, decode JWT to get new expiry time
        expiry_time = None
        if token:
            try:
                decoded = await self.decode_jwt(token)
                expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None
            except Exception:
                pass  # If JWT decode fails, keep expiry_time as None

        await self.db.update_token(token_id, token=token, password=password, st=st, rt=rt, client_id=client_id, proxy_url=proxy_url, remark=remark, expiry_time=expiry_time,
                                   image_enabled=image_enabled, video_enabled=video_enabled,
                                   image_concurrency=image_concurrency, video_concurrency=video_concurrency)

        # If token (AT) is updated and not in offline mode, test it and clear expired flag if valid
        if token and not skip_status_update:
            try:
                test_result = await self.test_token(token_id)
                if test_result.get("valid"):
                    # Token is valid, enable it and clear expired flag
                    await self.db.update_token_status(token_id, True)
                    await self.db.clear_token_expired(token_id)
            except Exception:
                pass  # Ignore test errors during update

    async def get_active_tokens(self) -> List[Token]:
        """Get all active tokens (not cooled down)"""
        return await self.db.get_active_tokens()
    
    async def get_all_tokens(self) -> List[Token]:
        """Get all tokens"""
        return await self.db.get_all_tokens()
    
    async def update_token_status(self, token_id: int, is_active: bool):
        """Update token active status"""
        await self.db.update_token_status(token_id, is_active)

    async def enable_token(self, token_id: int):
        """Enable a token and reset error count"""
        await self.db.update_token_status(token_id, True)
        # Reset error count when enabling (in token_stats table)
        await self.db.reset_error_count(token_id)
        # Clear expired flag when enabling
        await self.db.clear_token_expired(token_id)

    async def disable_token(self, token_id: int):
        """Disable a token"""
        await self.db.update_token_status(token_id, False)

    async def test_token(self, token_id: int) -> dict:
        """Test if a token is valid by calling Sora API and refresh account info (subscription + Sora2)"""
        # Get token from database
        token_data = await self.db.get_token(token_id)
        if not token_data:
            return {"valid": False, "message": "Token not found"}

        # Step 1: Try to refresh AT using ST or RT before testing
        access_token = token_data.token
        at_refreshed = False

        # Try ST first (preferred)
        if token_data.st:
            try:
                print(f"🔄 尝试用ST刷新AT...")
                st_result = await self.st_to_at(token_data.st, proxy_url=token_data.proxy_url)
                if st_result.get("access_token"):
                    access_token = st_result["access_token"]
                    # Update AT in database
                    decoded = await self.decode_jwt(access_token)
                    expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None
                    await self.db.update_token(token_id, token=access_token, expiry_time=expiry_time)
                    at_refreshed = True
                    print(f"✅ ST刷新AT成功")
            except Exception as e:
                print(f"⚠️ ST刷新AT失败: {e}")

        # Try RT if ST failed or not available
        if not at_refreshed and token_data.rt:
            try:
                print(f"🔄 尝试用RT刷新AT...")
                rt_result = await self.rt_to_at(token_data.rt, client_id=token_data.client_id, proxy_url=token_data.proxy_url)
                if rt_result.get("access_token"):
                    access_token = rt_result["access_token"]
                    new_rt = rt_result.get("refresh_token")
                    # Update AT and RT in database
                    decoded = await self.decode_jwt(access_token)
                    expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None
                    await self.db.update_token(token_id, token=access_token, rt=new_rt if new_rt else token_data.rt, expiry_time=expiry_time)
                    at_refreshed = True
                    print(f"✅ RT刷新AT成功")
            except Exception as e:
                print(f"⚠️ RT刷新AT失败: {e}")

        # Step 2: Test the token
        try:
            # Try to get user info from Sora API
            user_info = await self.get_user_info(access_token, token_id)

            # Extract phone verification status from my_info
            is_phone_verified = None
            my_info = user_info.get("my_info", {})
            if my_info:
                is_phone_verified = my_info.get("is_phone_number_verified")

            # Update phone verification status in database
            await self.db.update_token_phone_verified(token_id, is_phone_verified)

            # Get subscription info from Sora API
            plan_type = None
            plan_title = None
            subscription_end = None
            try:
                sub_info = await self.get_subscription_info(access_token, token_id)
                plan_type = sub_info.get("plan_type")
                plan_title = sub_info.get("plan_title")
                # Parse subscription end time
                if sub_info.get("subscription_end"):
                    from dateutil import parser
                    subscription_end = parser.parse(sub_info["subscription_end"])
            except Exception as e:
                print(f"Failed to get subscription info: {e}")

            # Refresh Sora2 invite code and counts
            sora2_info = await self.get_sora2_invite_code(access_token, token_id)
            sora2_supported = sora2_info.get("supported", False)
            sora2_invite_code = sora2_info.get("invite_code")
            sora2_redeemed_count = sora2_info.get("redeemed_count", 0)
            sora2_total_count = sora2_info.get("total_count", 0)
            sora2_remaining_count = 0

            # If Sora2 is supported, get remaining count
            if sora2_supported:
                try:
                    remaining_info = await self.get_sora2_remaining_count(access_token, token_id)
                    if remaining_info.get("success"):
                        sora2_remaining_count = remaining_info.get("remaining_count", 0)
                except Exception as e:
                    print(f"Failed to get Sora2 remaining count: {e}")

            # Update token subscription info in database
            await self.db.update_token(
                token_id,
                plan_type=plan_type,
                plan_title=plan_title,
                subscription_end=subscription_end
            )

            # Update token Sora2 info in database
            await self.db.update_token_sora2(
                token_id,
                supported=sora2_supported,
                invite_code=sora2_invite_code,
                redeemed_count=sora2_redeemed_count,
                total_count=sora2_total_count,
                remaining_count=sora2_remaining_count
            )

            # Clear expired flag if token is valid
            await self.db.clear_token_expired(token_id)

            return {
                "valid": True,
                "message": "Token is valid and account info updated",
                "email": user_info.get("email"),
                "username": user_info.get("username"),
                "plan_type": plan_type,
                "plan_title": plan_title,
                "subscription_end": subscription_end.isoformat() if subscription_end else None,
                "sora2_supported": sora2_supported,
                "sora2_invite_code": sora2_invite_code,
                "sora2_redeemed_count": sora2_redeemed_count,
                "sora2_total_count": sora2_total_count,
                "sora2_remaining_count": sora2_remaining_count,
                "is_phone_verified": is_phone_verified
            }
        except Exception as e:
            error_msg = str(e)
            # Check if error is 401 with token_invalidated
            if "401" in error_msg and "token_invalidated" in error_msg.lower():
                # Mark token as expired
                await self.db.mark_token_expired(token_id)
                return {
                    "valid": False,
                    "message": "Token已过期（token_invalidated）"
                }
            return {
                "valid": False,
                "message": f"Token is invalid: {error_msg}"
            }

    async def record_usage(self, token_id: int, is_video: bool = False):
        """Record token usage"""
        await self.db.update_token_usage(token_id)
        
        if is_video:
            await self.db.increment_video_count(token_id)
        else:
            await self.db.increment_image_count(token_id)
    
    async def record_error(self, token_id: int, is_overload: bool = False):
        """Record token error

        Args:
            token_id: Token ID
            is_overload: Whether this is an overload error (heavy_load). If True, only increment total error count.
        """
        await self.db.increment_error_count(token_id, increment_consecutive=not is_overload)

        # Check if should ban (only if not overload error)
        if not is_overload:
            stats = await self.db.get_token_stats(token_id)
            admin_config = await self.db.get_admin_config()

            if stats and stats.consecutive_error_count >= admin_config.error_ban_threshold:
                await self.db.update_token_status(token_id, False)
    
    async def record_success(self, token_id: int, is_video: bool = False):
        """Record successful request (reset error count)"""
        await self.db.reset_error_count(token_id)

        # Update Sora2 remaining count after video generation
        if is_video:
            try:
                token_data = await self.db.get_token(token_id)
                if token_data and token_data.sora2_supported:
                    remaining_info = await self.get_sora2_remaining_count(token_data.token, token_id)
                    if remaining_info.get("success"):
                        remaining_count = remaining_info.get("remaining_count", 0)
                        await self.db.update_token_sora2_remaining(token_id, remaining_count)
                        print(f"✅ 更新Token {token_id} 的Sora2剩余次数: {remaining_count}")

                        # If remaining count is 1 or less, disable token and set cooldown
                        if remaining_count <= 1:
                            reset_seconds = remaining_info.get("access_resets_in_seconds", 0)
                            if reset_seconds > 0:
                                cooldown_until = datetime.now() + timedelta(seconds=reset_seconds)
                                await self.db.update_token_sora2_cooldown(token_id, cooldown_until)
                                print(f"⏱️ Token {token_id} 剩余次数为{remaining_count}，设置冷却时间至: {cooldown_until}")
                            # Disable token
                            await self.disable_token(token_id)
                            print(f"🚫 Token {token_id} 剩余次数为{remaining_count}，已自动禁用")
            except Exception as e:
                print(f"Failed to update Sora2 remaining count: {e}")
    
    async def refresh_sora2_remaining_if_cooldown_expired(self, token_id: int):
        """Refresh Sora2 remaining count if cooldown has expired"""
        try:
            token_data = await self.db.get_token(token_id)
            if not token_data or not token_data.sora2_supported:
                return

            # Check if Sora2 cooldown has expired
            if token_data.sora2_cooldown_until and token_data.sora2_cooldown_until <= datetime.now():
                print(f"🔄 Token {token_id} Sora2冷却已过期，正在刷新剩余次数...")

                try:
                    remaining_info = await self.get_sora2_remaining_count(token_data.token, token_id)
                    if remaining_info.get("success"):
                        remaining_count = remaining_info.get("remaining_count", 0)
                        await self.db.update_token_sora2_remaining(token_id, remaining_count)
                        # Clear cooldown
                        await self.db.update_token_sora2_cooldown(token_id, None)
                        print(f"✅ Token {token_id} Sora2剩余次数已刷新: {remaining_count}")
                except Exception as e:
                    print(f"Failed to refresh Sora2 remaining count: {e}")
        except Exception as e:
            print(f"Error in refresh_sora2_remaining_if_cooldown_expired: {e}")

    async def auto_refresh_expiring_token(self, token_id: int) -> bool:
        """
        Auto refresh token when expiry time is within 24 hours using ST or RT

        Returns:
            True if refresh successful, False otherwise
        """
        try:
            # 📍 Step 1: 获取Token数据
            debug_logger.log_info(f"[AUTO_REFRESH] 开始检查Token {token_id}...")
            token_data = await self.db.get_token(token_id)

            if not token_data:
                debug_logger.log_info(f"[AUTO_REFRESH] ❌ Token {token_id} 不存在")
                return False

            # 📍 Step 2: 检查是否有过期时间
            if not token_data.expiry_time:
                debug_logger.log_info(f"[AUTO_REFRESH] ⏭️  Token {token_id} 无过期时间，跳过刷新")
                return False  # No expiry time set

            # 📍 Step 3: 计算剩余时间
            time_until_expiry = token_data.expiry_time - datetime.now()
            hours_until_expiry = time_until_expiry.total_seconds() / 3600

            debug_logger.log_info(f"[AUTO_REFRESH] ⏰ Token {token_id} 信息:")
            debug_logger.log_info(f"  - Email: {token_data.email}")
            debug_logger.log_info(f"  - 过期时间: {token_data.expiry_time.strftime('%Y-%m-%d %H:%M:%S')}")
            debug_logger.log_info(f"  - 剩余时间: {hours_until_expiry:.2f} 小时")
            debug_logger.log_info(f"  - 是否激活: {token_data.is_active}")
            debug_logger.log_info(f"  - 有ST: {'是' if token_data.st else '否'}")
            debug_logger.log_info(f"  - 有RT: {'是' if token_data.rt else '否'}")

            # 📍 Step 4: 检查是否需要刷新
            if hours_until_expiry > 24:
                debug_logger.log_info(f"[AUTO_REFRESH] ⏭️  Token {token_id} 剩余时间 > 24小时，无需刷新")
                return False  # Token not expiring soon

            # 📍 Step 5: 触发刷新
            if hours_until_expiry < 0:
                debug_logger.log_info(f"[AUTO_REFRESH] 🔴 Token {token_id} 已过期，尝试自动刷新...")
            else:
                debug_logger.log_info(f"[AUTO_REFRESH] 🟡 Token {token_id} 将在 {hours_until_expiry:.2f} 小时后过期，尝试自动刷新...")

            # Priority: ST > RT
            new_at = None
            new_st = None
            new_rt = None
            refresh_method = None

            # 📍 Step 6: 尝试使用ST刷新
            if token_data.st:
                try:
                    debug_logger.log_info(f"[AUTO_REFRESH] 📝 Token {token_id}: 尝试使用 ST 刷新...")
                    result = await self.st_to_at(token_data.st)
                    new_at = result.get("access_token")
                    new_st = token_data.st  # ST refresh doesn't return new ST, so keep the old one
                    refresh_method = "ST"
                    debug_logger.log_info(f"[AUTO_REFRESH] ✅ Token {token_id}: 使用 ST 刷新成功")
                except Exception as e:
                    debug_logger.log_info(f"[AUTO_REFRESH] ❌ Token {token_id}: 使用 ST 刷新失败 - {str(e)}")
                    new_at = None

            # 📍 Step 7: 如果ST失败，尝试使用RT
            if not new_at and token_data.rt:
                try:
                    debug_logger.log_info(f"[AUTO_REFRESH] 📝 Token {token_id}: 尝试使用 RT 刷新...")
                    result = await self.rt_to_at(token_data.rt, client_id=token_data.client_id)
                    new_at = result.get("access_token")
                    new_rt = result.get("refresh_token", token_data.rt)  # RT might be updated
                    refresh_method = "RT"
                    debug_logger.log_info(f"[AUTO_REFRESH] ✅ Token {token_id}: 使用 RT 刷新成功")
                except Exception as e:
                    debug_logger.log_info(f"[AUTO_REFRESH] ❌ Token {token_id}: 使用 RT 刷新失败 - {str(e)}")
                    new_at = None

            # 📍 Step 8: 处理刷新结果
            if new_at:
                # 刷新成功: 更新Token
                debug_logger.log_info(f"[AUTO_REFRESH] 💾 Token {token_id}: 保存新的 Access Token...")
                await self.update_token(token_id, token=new_at, st=new_st, rt=new_rt)

                # 获取更新后的Token信息
                updated_token = await self.db.get_token(token_id)
                new_expiry_time = updated_token.expiry_time
                new_hours_until_expiry = ((new_expiry_time - datetime.now()).total_seconds() / 3600) if new_expiry_time else -1

                debug_logger.log_info(f"[AUTO_REFRESH] ✅ Token {token_id} 已自动刷新成功")
                debug_logger.log_info(f"  - 刷新方式: {refresh_method}")
                debug_logger.log_info(f"  - 新过期时间: {new_expiry_time.strftime('%Y-%m-%d %H:%M:%S') if new_expiry_time else 'N/A'}")
                debug_logger.log_info(f"  - 新剩余时间: {new_hours_until_expiry:.2f} 小时")

                # 📍 Step 9: 检查刷新后的过期时间
                if new_hours_until_expiry < 0:
                    # 刷新后仍然过期，禁用Token
                    debug_logger.log_info(f"[AUTO_REFRESH] 🔴 Token {token_id}: 刷新后仍然过期（剩余时间: {new_hours_until_expiry:.2f} 小时），已禁用")
                    await self.disable_token(token_id)
                    return False

                return True
            else:
                # 刷新失败: 禁用Token
                debug_logger.log_info(f"[AUTO_REFRESH] 🚫 Token {token_id}: 无法刷新（无有效的 ST 或 RT），已禁用")
                await self.disable_token(token_id)
                return False

        except Exception as e:
            debug_logger.log_info(f"[AUTO_REFRESH] 🔴 Token {token_id}: 自动刷新异常 - {str(e)}")
            return False
