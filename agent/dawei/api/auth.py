"""
Authentication API for DavyBot
认证 API - 处理 OAuth2 回调和用户会话管理
"""

import secrets
import httpx
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, Cookie, status
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel

from dawei import get_dawei_home
from dawei.config.settings import get_settings



router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ========== Configuration ==========

# Support System OAuth配置
settings = get_settings()
support_config = settings.support_system
SUPPORT_SYSTEM_URL = support_config.url
OAUTH_CLIENT_ID = support_config.oauth_client_id
OAUTH_CLIENT_SECRET = support_config.oauth_client_secret
OAUTH_REDIRECT_URI = support_config.oauth_redirect_uri

# Session 配置
SESSION_COOKIE_NAME = "davybot_session"
SESSION_MAX_AGE = 7 * 24 * 60 * 60  # 7天 (秒)


# ========== Data Models ==========

class UserInfo(BaseModel):
    """用户信息"""
    id: str
    email: str
    nickname: str
    avatar: Optional[str] = None
    token_quota: int
    token_used: int
    is_active: bool


class UserResponse(BaseModel):
    """用户信息响应"""
    authenticated: bool
    user: Optional[UserInfo] = None


class LogoutResponse(BaseModel):
    """登出响应"""
    success: bool
    message: str


# ========== Session Management ==========

class SessionManager:
    """会话管理器"""

    def __init__(self):
        self.sessions_dir = get_dawei_home() / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_file(self, session_id: str) -> Path:
        """获取session文件路径"""
        return self.sessions_dir / f"{session_id}.json"

    async def create_session(self, user_data: dict, tokens: dict) -> str:
        """创建新session

        Args:
            user_data: 用户数据
            tokens: Token数据 (access_token, refresh_token)

        Returns:
            str: Session ID
        """
        import json
        from datetime import datetime, timedelta

        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(seconds=SESSION_MAX_AGE)

        session_data = {
            "session_id": session_id,
            "user": user_data,
            "tokens": tokens,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat()
        }

        # 保存到文件
        session_file = self._get_session_file(session_id)
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)

        return session_id

    async def get_session(self, session_id: str) -> Optional[dict]:
        """获取session

        Args:
            session_id: Session ID

        Returns:
            dict: Session数据（如果存在且未过期）
        """
        import json
        from datetime import datetime

        session_file = self._get_session_file(session_id)

        if not session_file.exists():
            return None

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            # 检查是否过期
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            if datetime.utcnow() > expires_at:
                # 过期，删除session
                await self.delete_session(session_id)
                return None

            return session_data

        except Exception as e:
            print(f"Error reading session: {e}")
            return None

    async def delete_session(self, session_id: str) -> None:
        """删除session

        Args:
            session_id: Session ID
        """
        session_file = self._get_session_file(session_id)

        if session_file.exists():
            session_file.unlink()

    async def get_session_by_user_id(self, user_id: str) -> Optional[dict]:
        """通过用户ID获取session

        Args:
            user_id: 用户ID

        Returns:
            dict: Session数据
        """
        # 遍历所有session文件（简单实现，生产环境应使用数据库）
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                import json
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

                if session_data.get("user", {}).get("id") == user_id:
                    # 检查是否过期
                    from datetime import datetime
                    expires_at = datetime.fromisoformat(session_data["expires_at"])
                    if datetime.utcnow() <= expires_at:
                        return session_data
            except:
                continue

        return None


# 全局 session 管理器
session_manager = SessionManager()


# ========== Helper Functions ==========

async def get_current_session(request: Request) -> Optional[dict]:
    """从cookie中获取当前session

    Args:
        request: FastAPI 请求对象

    Returns:
        dict: Session数据
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        return None

    return await session_manager.get_session(session_id)


async def exchange_code_for_token(code: str) -> dict:
    """使用授权码交换access token

    Args:
        code: 授权码

    Returns:
        dict: 包含 access_token 和用户信息的响应

    Raises:
        HTTPException: 如果交换失败
    """
    token_url = f"{SUPPORT_SYSTEM_URL}/support/auth/oauth/token"

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "redirect_uri": OAUTH_REDIRECT_URI
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(token_url, json=payload, timeout=10.0)
            response.raise_for_status()

            return response.json()

        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code for token: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error exchanging code for token: {str(e)}"
            )


# ========== API Endpoints ==========

@router.get("/callback", status_code=status.HTTP_200_OK)
async def oauth_callback(
    request: Request,
    code: str,
    state: Optional[str] = None
):
    """
    OAuth2 回调端点

    1. 接收授权码
    2. 向Support System交换token
    3. 创建session
    4. 返回成功页面

    Args:
        request: FastAPI 请求对象
        code: 授权码
        state: 状态令牌（可选，用于验证）

    Returns:
        HTMLResponse: 成功页面（JavaScript通知主窗口）
    """

    try:
        # 1. 交换授权码获取token
        token_response = await exchange_code_for_token(code)

        # 2. 提取用户信息和token
        user_data = token_response.get("user", {})
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")

        if not user_data or not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token response"
            )

        # 3. 创建session
        session_id = await session_manager.create_session(
            user_data=user_data,
            tokens={
                "access_token": access_token,
                "refresh_token": refresh_token
            }
        )

        # 4. 返回成功页面（设置cookie并通知主窗口）
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>登录成功</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }}
                .container {{
                    text-align: center;
                    padding: 40px;
                }}
                h1 {{
                    font-size: 48px;
                    margin-bottom: 20px;
                }}
                p {{
                    font-size: 18px;
                    opacity: 0.9;
                }}
                .spinner {{
                    border: 4px solid rgba(255,255,255,0.3);
                    border-top: 4px solid white;
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    animation: spin 1s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✓</h1>
                <h2>登录成功</h2>
                <p>正在返回应用...</p>
                <div class="spinner"></div>
            </div>

            <script>
            // 通知主窗口登录成功
            if (window.opener) {{
                window.opener.postMessage({{
                    type: 'oauth_login_success',
                    data: {{
                        session_id: '{session_id}',
                        user: {str(user_data).replace("'", '"')}
                    }}
                }}, '*');

                // 延迟关闭窗口
                setTimeout(() => {{
                    window.close();
                }}, 1000);
            }} else {{
                // 如果没有opener，重定向到主页
                window.location.href = '/?session_id={session_id}';
            }}
            </script>
        </body>
        </html>
        """

        response = HTMLResponse(content=html_content)

        # 设置session cookie
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            max_age=SESSION_MAX_AGE,
            httponly=True,  # 防止XSS
            samesite="lax"  # 防止CSRF
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        # 返回错误页面
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>登录失败</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    color: white;
                }}
                .container {{
                    text-align: center;
                    padding: 40px;
                }}
                h1 {{
                    font-size: 48px;
                    margin-bottom: 20px;
                }}
                p {{
                    font-size: 18px;
                    opacity: 0.9;
                }}
                .error {{
                    background: rgba(0,0,0,0.2);
                    padding: 20px;
                    border-radius: 10px;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✗</h1>
                <h2>登录失败</h2>
                <p>无法完成登录，请关闭此窗口并重试</p>
                <div class="error">
                    <strong>错误信息:</strong><br>
                    {str(e)}
                </div>
            </div>

            <script>
            // 通知主窗口登录失败
            if (window.opener) {{
                window.opener.postMessage({{
                    type: 'oauth_login_error',
                    error: '{str(e)}'
                }}, '*');

                setTimeout(() => {{
                    window.close();
                }}, 3000);
            }}
            </script>
        </body>
        </html>
        """

        return HTMLResponse(content=html_content, status_code=400)


@router.get("/user", response_model=UserResponse)
async def get_user(request: Request):
    """
    获取当前登录用户信息

    Args:
        request: FastAPI 请求对象

    Returns:
        UserResponse: 用户信息响应
    """
    session = await get_current_session(request)

    if not session:
        return UserResponse(authenticated=False, user=None)

    user_data = session.get("user")

    return UserResponse(
        authenticated=True,
        user=UserInfo(**user_data)
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(request: Request, response: Response):
    """
    登出当前用户

    Args:
        request: FastAPI 请求对象
        response: FastAPI 响应对象

    Returns:
        LogoutResponse: 登出响应
    """
    session = await get_current_session(request)

    if session:
        session_id = session.get("session_id")
        if session_id:
            await session_manager.delete_session(session_id)

    # 清除cookie
    response.delete_cookie(SESSION_COOKIE_NAME)

    return LogoutResponse(
        success=True,
        message="Logged out successfully"
    )


@router.get("/login")
async def login_page():
    """
    登录页面（用于测试）

    实际使用中，客户端应该直接打开OAuth授权URL
    """
    auth_url = (
        f"{SUPPORT_SYSTEM_URL}/support/auth/oauth/authorize"
        f"?client_id={OAUTH_CLIENT_ID}"
        f"&redirect_uri={OAUTH_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=profile"
    )

    return RedirectResponse(url=auth_url, status_code=302)
