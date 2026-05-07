"""
Anuma AI Client — Privy authentication and chat API SDK.
"""

import time
import json
import base64
import uuid
from typing import Dict, Any, List, Optional, Callable

import requests

def get_jwt_expiry(token: str) -> Optional[int]:
    try:
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64))
        return payload.get("exp")
    except: return None

class TemporaryMailClient:
    def __init__(self, api_key: str, base_url: str = "https://maliapi.215.im/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.account_id, self.address, self.temp_token, self.proxies = None, None, None, None

    def create_account(self, local_part: str, domain: Optional[str] = None) -> Dict[str, Any]:
        payload = {"localPart": local_part}
        if domain: payload["domain"] = domain
        kwargs = {"headers": {"X-API-Key": self.api_key}, "json": payload}
        if self.proxies: kwargs["proxies"] = self.proxies
        res = requests.post(f"{self.base_url}/accounts", **kwargs).json()
        if res.get("success"):
            data = res.get("data", {})
            self.account_id = data.get("id")
            self.address = data.get("address")
            self.temp_token = data.get("token") or data.get("access_token") or data.get("tempToken") or res.get("token")
        return res

    def _mail_headers(self) -> Dict[str, str]:
        headers = {"X-API-Key": self.api_key}
        if self.temp_token:
            headers["Authorization"] = f"Bearer {self.temp_token}"
        return headers

    def get_messages_response(self) -> Dict[str, Any]:
        kwargs = {"headers": self._mail_headers(), "params": {"address": self.address}}
        if self.proxies: kwargs["proxies"] = self.proxies
        return requests.get(f"{self.base_url}/messages", **kwargs).json()

    def get_messages(self) -> List[Dict[str, Any]]:
        res = self.get_messages_response()
        data = res.get("data", {})
        if isinstance(data, dict):
            return data.get("messages", [])
        if isinstance(data, list):
            return data
        return []

    def get_message(self, message_id: str) -> Dict[str, Any]:
        kwargs = {"headers": self._mail_headers(), "params": {"address": self.address}}
        if self.proxies: kwargs["proxies"] = self.proxies
        return requests.get(f"{self.base_url}/messages/{message_id}", **kwargs).json()

    def wait_for_code(self, timeout: int = 120, progress: Optional[Callable[[str], None]] = None) -> str:
        import re
        start = time.time()
        last_log = 0
        while time.time() - start < timeout:
            elapsed = int(time.time() - start)
            try:
                res = self.get_messages_response()
            except Exception as e:
                if progress and elapsed - last_log >= 10:
                    progress(f"查询邮箱失败: {e}")
                    last_log = elapsed
                time.sleep(3)
                continue

            data = res.get("data", {}) if isinstance(res, dict) else {}
            if isinstance(data, dict):
                messages = data.get("messages", [])
            elif isinstance(data, list):
                messages = data
            else:
                messages = []

            if progress and elapsed - last_log >= 10:
                if isinstance(res, dict) and not res.get("success", True):
                    progress(f"邮箱接口错误: {res.get('error') or res.get('errorCode') or res}")
                else:
                    progress(f"等待邮箱验证码中... {elapsed}s，当前邮件 {len(messages)} 封")
                last_log = elapsed

            for msg in messages:
                message_id = msg.get("id") or msg.get("messageId")
                if not message_id:
                    continue
                detail = self.get_message(message_id).get("data", {})
                text = detail.get("text") or detail.get("body") or detail.get("html") or msg.get("text") or msg.get("subject") or ""
                code = re.search(r'\b(\d{6})\b', text)
                if code: return code.group(1)
            time.sleep(3)
        raise TimeoutError("Timeout")

class AnumaClient:
    def __init__(self, mail_api_key: str, proxies: Optional[Dict[str, str]] = None,
                 mail_proxies: Optional[Dict[str, str]] = None,
                 mail_base_url: str = "https://maliapi.215.im/v1"):
        self.api_key = mail_api_key
        self.mail_client = TemporaryMailClient(mail_api_key, base_url=mail_base_url)
        self.mail_client.proxies = mail_proxies
        self.proxies = proxies or {}
        self.session = requests.Session()
        if proxies: self.session.proxies.update(proxies)
        self.privy_auth_url = "https://auth.privy.io/api/v1"
        self.portal_url = "https://portal.anuma.ai/api/v1"
        self.chat_url = "https://chat.anuma.ai/api"
        self.identity_token, self.privy_access_token, self.refresh_token = None, None, None
        self.wallet_address = None

    def _get_headers(self, with_auth: bool = True) -> Dict[str, str]:
        # 完全模仿成功 curl 的 Headers
        headers = {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://chat.anuma.ai",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://chat.anuma.ai/",
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "sec-fetch-storage-access": "active",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "x-privacy-mode": "standard" # 改为作为 Header
        }
        headers["privy-app-id"] = "cmjrfihuc03h8l10ca0bi9o2y"
        headers["privy-client"] = "react-auth:3.14.1"
        headers["privy-ca-id"] = str(uuid.uuid4())
        if with_auth and self.identity_token:
            headers["authorization"] = f"Bearer {self.identity_token}"
        return headers

    def _json_or_error(self, resp, label: str) -> Dict[str, Any]:
        try:
            data = resp.json()
        except Exception:
            data = {"text": resp.text[:500]}
        if resp.status_code != 200:
            raise Exception(f"{label} failed: HTTP {resp.status_code}, {data}")
        if isinstance(data, dict) and data.get("error"):
            raise Exception(f"{label} failed: {data}")
        return data

    def signup(self, mailbox_local_part: Optional[str] = None, domain: Optional[str] = None, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        def log_step(message: str):
            if progress:
                progress(message)

        if not mailbox_local_part: mailbox_local_part = f"anuma_{int(time.time())}"
        log_step(f"创建临时邮箱: {mailbox_local_part}{'@' + domain if domain else ''}")
        mail_res = self.mail_client.create_account(mailbox_local_part, domain=domain)
        if not mail_res.get("success"):
            if not domain:
                log_step("默认邮箱域名创建失败，切换到 0m0.app")
                mail_res = self.mail_client.create_account(mailbox_local_part, domain="0m0.app")
            if not mail_res.get("success"): raise Exception(f"Mail Error: {mail_res}")
        email = self.mail_client.address
        log_step(f"邮箱创建成功: {email}")
        s = self.session
        log_step("初始化 Privy 会话")
        s.post(f"{self.privy_auth_url}/analytics_events", headers=self._get_headers(False), json={"event_name": "sdk_initialize", "client_id": "582a28dc-edef-4b36-b2e1-cd1662bd3494", "payload": {"embeddedWallets": {"ethereum": {"createOnLogin": "all-users"}}, "supportedChains": [7001], "clientTimestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}} )
        log_step("发送邮箱验证码")
        init_resp = s.post(f"{self.privy_auth_url}/passwordless/init", headers=self._get_headers(False), json={"email": email})
        try:
            init_data = init_resp.json()
        except Exception:
            init_data = {"text": init_resp.text[:300]}
        if init_resp.status_code != 200:
            raise Exception(f"Passwordless init failed: HTTP {init_resp.status_code}, {init_data}")
        if isinstance(init_data, dict) and (init_data.get("error") or init_data.get("message")):
            log_step(f"验证码发送响应: {init_data.get('error') or init_data.get('message')}")
        else:
            log_step("验证码发送请求成功")
        code = self.mail_client.wait_for_code(progress=log_step)
        log_step("收到邮箱验证码，开始登录")
        auth_res = self._json_or_error(
            s.post(f"{self.privy_auth_url}/passwordless/authenticate", headers=self._get_headers(False), json={"email": email, "code": code, "mode": "login-or-sign-up"}),
            "Passwordless authenticate"
        )
        if "refresh_token" not in auth_res or "privy_access_token" not in auth_res:
            raise Exception(f"Passwordless authenticate failed: {auth_res}")
        self.refresh_token = auth_res["refresh_token"]
        self.privy_access_token = auth_res["privy_access_token"]
        log_step("刷新 identity token")
        sess_res = self._json_or_error(
            s.post(f"{self.privy_auth_url}/sessions", headers={"Authorization": f"Bearer {self.privy_access_token}", **self._get_headers(False)}, json={"refresh_token": self.refresh_token}),
            "Create session"
        )
        if "identity_token" not in sess_res:
            raise Exception(f"Create session failed: {sess_res}")
        self.identity_token = sess_res["identity_token"]
        self.privy_access_token = sess_res.get("privy_access_token", self.privy_access_token)
        log_step("创建钱包")
        wallet_res = self._json_or_error(
            s.post(f"{self.privy_auth_url}/wallets", headers={"Authorization": f"Bearer {sess_res['privy_access_token']}", **self._get_headers(False)}, json={"chain_type": "ethereum"}),
            "Create wallet"
        )
        self.wallet_address = wallet_res.get("address") or wallet_res.get("data", {}).get("address")
        log_step("同步钱包信息")
        final_sess = self._json_or_error(
            s.post(f"{self.privy_auth_url}/sessions", headers={"Authorization": f"Bearer {sess_res['privy_access_token']}", **self._get_headers(False)}, json={"refresh_token": self.refresh_token}),
            "Refresh session"
        )
        if "identity_token" not in final_sess:
            raise Exception(f"Refresh session failed: {final_sess}")
        self.identity_token = final_sess["identity_token"]
        self.privy_access_token = final_sess.get("privy_access_token", self.privy_access_token)
        self.refresh_token = final_sess.get("refresh_token", self.refresh_token)
        log_step("查询额度")
        return {"email": email, "credits": self.get_balance(), "access_token": self.privy_access_token, "identity_token": self.identity_token}

    def refresh_id_token(self, refresh_token: str, access_token: str) -> str:
        headers = self._get_headers(False)
        headers.update({
            "authorization": f"Bearer {access_token}",
            "accept": "application/json",
            "privy-app-id": "cmjrfihuc03h8l10ca0bi9o2y",
            "privy-client": "react-auth:3.14.1",
            "privy-ca-id": str(uuid.uuid4()),
            "sec-fetch-site": "cross-site",
            "sec-fetch-storage-access": "active",
        })
        resp = self.session.post(f"{self.privy_auth_url}/sessions", headers=headers, json={"refresh_token": refresh_token})
        try:
            res = resp.json()
        except Exception:
            raise Exception(f"Refresh Error: HTTP {resp.status_code}, {resp.text[:500]}")

        if resp.status_code != 200 or "identity_token" not in res:
            err = res.get("error") or res.get("message") or res.get("code") or res
            raise Exception(f"Refresh Error: HTTP {resp.status_code}, {err}")

        self.identity_token = res["identity_token"]
        self.privy_access_token = res.get("privy_access_token", access_token)
        self.refresh_token = res.get("refresh_token", refresh_token)
        return self.identity_token

    def _prepare_payload(self, messages, model, max_tokens, stream, tools):
        anuma_input = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str): c_block = [{"type": "text", "text": content}]
            else:
                c_block = []
                for b in content:
                    if b.get("type") == "text": c_block.append({"type": "text", "text": b.get("text", "")})
                    elif b.get("type") == "tool_use": c_block.append({"type": "tool_call", "id": b.get("id"), "name": b.get("name"), "parameters": b.get("input", {})})
                    elif b.get("type") == "tool_result": c_block.append({"type": "tool_result", "tool_use_id": b.get("tool_use_id"), "content": b.get("content") if isinstance(b.get("content"), str) else json.dumps(b.get("content"))})
            anuma_input.append({"role": msg["role"], "content": c_block})

        payload = {
            "input": anuma_input,
            "model": model,
            "stream": stream,
            "max_output_tokens": max_tokens,
            "conversation_id": str(uuid.uuid4())
        }
        # if tools: payload["tools"] = tools # 这里在 api_server 会过滤掉，但这层保留兼容性
        return payload

    def chat_stream(self, messages, model, max_tokens=32000, tools=None):
        payload = self._prepare_payload(messages, model, max_tokens, True, tools)
        res = self.session.post(f"{self.portal_url}/responses", headers=self._get_headers(), json=payload, stream=True)
        if res.status_code != 200: raise Exception(f"Chat Error: {res.text}")
        for line in res.iter_lines():
            if line:
                line_s = line.decode('utf-8')
                if line_s.startswith('data: '):
                    data = line_s[6:]
                    if data.strip() and data.strip() != '[DONE]':
                        try: yield json.loads(data)
                        except: continue

    def chat(self, messages, model, stream=False, max_tokens=32000, tools=None):
        payload = self._prepare_payload(messages, model, max_tokens, False, tools)
        res = self.session.post(f"{self.portal_url}/responses", headers=self._get_headers(), json=payload)
        if res.status_code != 200: raise Exception(f"Chat Error: {res.text}")
        return res.json()

    def get_balance(self):
        res = self.session.get(f"{self.portal_url}/credits/balance", headers=self._get_headers())
        if res.status_code != 200: raise Exception(f"Balance Error: {res.text}")
        return res.json()
