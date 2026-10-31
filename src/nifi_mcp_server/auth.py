from __future__ import annotations

import base64
from typing import Optional

import requests


class KnoxAuthFactory:
	def __init__(
		self,
		gateway_url: str,
		token: Optional[str],
		cookie: Optional[str],
		user: Optional[str],
		password: Optional[str],
		token_endpoint: Optional[str],
		passcode_token: Optional[str],
		verify: bool | str,
		nifi_api_base: Optional[str] = None,
		nifi_user: Optional[str] = None,
		nifi_password: Optional[str] = None,
		client_cert: Optional[str] = None,
		client_key: Optional[str] = None,
	):
		self.gateway_url = gateway_url.rstrip("/") if gateway_url else ""
		self.token = token
		self.cookie = cookie
		self.user = user
		self.password = password
		self.token_endpoint = token_endpoint or (
			f"{self.gateway_url}/knoxtoken/api/v1/token" if self.gateway_url else None
		)
		self.passcode_token = passcode_token
		self.verify = verify
		# Standalone / local NiFi (no Knox in front)
		self.nifi_api_base = nifi_api_base.rstrip("/") if nifi_api_base else None
		self.nifi_user = nifi_user
		self.nifi_password = nifi_password
		self.client_cert = client_cert
		self.client_key = client_key

	def build_session(self) -> requests.Session:
		session = requests.Session()
		session.verify = self.verify

		# Priority: Explicit Cookie -> Knox token (as cookie for CDP) -> mTLS client cert
		# -> Passcode token -> Knox basic creds token exchange -> local NiFi login -> anonymous
		if self.cookie:
			session.headers["Cookie"] = self.cookie
			return session

		if self.token:
			# For CDP NiFi, Knox JWT tokens must be sent as cookies, not Bearer headers
			session.headers["Cookie"] = f"hadoop-jwt={self.token}"
			return session

		if self.client_cert and self.client_key:
			# mTLS: NiFi identifies the caller from the client certificate, no bearer token needed
			session.cert = (self.client_cert, self.client_key)
			return session

		if self.passcode_token:
			# Prefer exchanging passcode for JWT via knoxtoken endpoint when available
			if self.token_endpoint:
				jwt = self._exchange_passcode_for_jwt()
				session.headers["Authorization"] = f"Bearer {jwt}"
				return session
			# Fallback: send passcode as header (may not work on all deployments)
			session.headers["X-Knox-Passcode"] = self.passcode_token
			return session

		if self.user and self.password and self.token_endpoint:
			jwt = self._fetch_knox_token()
			session.headers["Authorization"] = f"Bearer {jwt}"
			return session

		if self.nifi_user and self.nifi_password and self.nifi_api_base:
			# Standalone NiFi (single-user or LDAP/OIDC-via-login-identity-provider):
			# POST credentials directly to NiFi's own /access/token endpoint.
			jwt = self._fetch_nifi_token()
			session.headers["Authorization"] = f"Bearer {jwt}"
			return session

		# No credentials configured: anonymous session (fine for NiFi instances
		# running with anonymous access enabled, e.g. local/dev deployments).
		return session

	def _fetch_nifi_token(self) -> str:
		"""Login directly against a standalone NiFi's /access/token endpoint."""
		resp = requests.post(
			f"{self.nifi_api_base}/access/token",
			data={"username": self.nifi_user, "password": self.nifi_password},
			headers={"Content-Type": "application/x-www-form-urlencoded"},
			verify=self.verify,
			timeout=15,
		)
		resp.raise_for_status()
		# NiFi returns the raw JWT as the response body (text/plain), not JSON
		return resp.text.strip()

	def _fetch_knox_token(self) -> str:
		# Default Knox token endpoint returns raw JWT or JSON with token fields
		resp = requests.get(
			self.token_endpoint,
			auth=(self.user, self.password),
			verify=self.verify,
			timeout=15,
		)
		resp.raise_for_status()
		try:
			data = resp.json()
			return data.get("access_token") or data.get("token") or data.get("accessToken")
		except ValueError:
			text = resp.text.strip()
			# Some envs return Base64-encoded token; detect and decode if needed
			try:
				decoded = base64.b64decode(text).decode("utf-8")
				if decoded.count(".") == 2:
					return decoded
			except Exception:
				pass
			return text

	def _exchange_passcode_for_jwt(self) -> str:
		"""Exchange Knox passcode token for JWT using Basic auth pattern passcode:<token>."""
		if not (self.passcode_token and self.token_endpoint):
			raise RuntimeError("Passcode token exchange requires token_endpoint and passcode token")
		import base64
		header = {
			"Authorization": "Basic " + base64.b64encode(f"passcode:{self.passcode_token}".encode()).decode(),
			"X-Requested-By": "nifi-mcp-server",
		}
		resp = requests.get(self.token_endpoint, headers=header, verify=self.verify, timeout=15)
		resp.raise_for_status()
		try:
			data = resp.json()
			return data.get("access_token") or data.get("token") or data.get("accessToken")
		except ValueError:
			return resp.text.strip()


