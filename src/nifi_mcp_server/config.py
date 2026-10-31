from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ServerConfig:
	# Transport: stdio (default), http, sse
	transport: str = os.getenv("MCP_TRANSPORT", "stdio")
	host: str = os.getenv("MCP_HOST", "127.0.0.1")
	port: int = int(os.getenv("MCP_PORT", "3030"))

	# Knox + NiFi
	knox_gateway_url: str = os.getenv("KNOX_GATEWAY_URL", "")
	nifi_api_base: Optional[str] = os.getenv("NIFI_API_BASE")

	# Auth options (Knox / CDP)
	knox_token: Optional[str] = os.getenv("KNOX_TOKEN")
	knox_cookie: Optional[str] = os.getenv("KNOX_COOKIE")
	knox_user: Optional[str] = os.getenv("KNOX_USER")
	knox_password: Optional[str] = os.getenv("KNOX_PASSWORD")
	knox_token_endpoint: Optional[str] = os.getenv("KNOX_TOKEN_ENDPOINT")

	# Optional passcode token (e.g., Livy/Knox) for alternate auth patterns
	knox_passcode_token: Optional[str] = os.getenv("KNOX_PASSCODE_TOKEN")

	# Auth options (standalone / local NiFi, no Knox in front)
	# Single-user or LDAP login against NiFi's own /access/token endpoint
	nifi_username: Optional[str] = os.getenv("NIFI_USERNAME")
	nifi_password: Optional[str] = os.getenv("NIFI_PASSWORD")
	# mTLS client certificate auth against NiFi directly
	nifi_client_cert: Optional[str] = os.getenv("NIFI_CLIENT_CERT")
	nifi_client_key: Optional[str] = os.getenv("NIFI_CLIENT_KEY")

	# TLS/HTTP
	verify_ssl_env: str = os.getenv("KNOX_VERIFY_SSL", "true").lower()
	ca_bundle: Optional[str] = os.getenv("KNOX_CA_BUNDLE")
	timeout_seconds: int = int(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))
	max_retries: int = int(os.getenv("HTTP_MAX_RETRIES", "3"))
	rate_limit_rps: float = float(os.getenv("HTTP_RATE_LIMIT_RPS", "5"))

	# Behavior
	readonly: bool = os.getenv("NIFI_READONLY", "true").lower() == "true"
	allowed_actions_csv: str = os.getenv("NIFI_ALLOWED_ACTIONS", "")
	
	# CDP-specific proxy headers
	proxy_context_path: Optional[str] = os.getenv("NIFI_PROXY_CONTEXT_PATH")

	def build_verify(self) -> bool | str:
		if self.ca_bundle:
			return self.ca_bundle
		return self.verify_ssl_env not in {"0", "false", "no"}

	def build_nifi_base(self) -> str:
		if self.nifi_api_base:
			return self.nifi_api_base.rstrip("/")
		if not self.knox_gateway_url:
			raise ValueError("KNOX_GATEWAY_URL or NIFI_API_BASE must be set")
		return f"{self.knox_gateway_url.rstrip('/')}/nifi-api"


