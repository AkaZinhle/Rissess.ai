# =============================================================================
# Rissess.AI — Dify API Bridge
# dify_client.py
#
# Provides a robust Python client for the Dify Chat-Message API.
# Supports both streaming (SSE) and blocking response modes, session
# management, retry logic, and structured error handling.
# =============================================================================

import os
import json
import uuid
import logging
from typing import Generator, Optional

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("rissess_ai.dify_client")


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class DifyAPIError(Exception):
    """Raised when the Dify API returns a non-2xx status or an error payload."""
    def __init__(self, message: str, status_code: int = None, raw: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw

    def __str__(self):
        base = super().__str__()
        if self.status_code:
            return f"[HTTP {self.status_code}] {base}"
        return base


class DifyAuthError(DifyAPIError):
    """Raised on 401 Unauthorized — bad or missing API key."""
    pass


class DifyRateLimitError(DifyAPIError):
    """Raised on 429 Too Many Requests."""
    pass


class DifyStreamError(DifyAPIError):
    """Raised when an error event is received inside an SSE stream."""
    pass


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------

class SessionManager:
    """
    Manages conversation sessions so the Dify agent maintains context
    across multiple turns within the same user session.

    Sessions are stored in-memory (dict). For production, replace with
    Redis or a database-backed store.
    """

    def __init__(self):
        self._sessions: dict[str, str] = {}  # user_id -> conversation_id

    def get_conversation_id(self, user_id: str) -> Optional[str]:
        """Return the Dify conversation_id for a given user, or None if new."""
        return self._sessions.get(user_id)

    def set_conversation_id(self, user_id: str, conversation_id: str) -> None:
        """Persist the conversation_id returned by the Dify API."""
        self._sessions[user_id] = conversation_id
        logger.debug(f"Session updated — user={user_id}, conv={conversation_id}")

    def clear_session(self, user_id: str) -> None:
        """Reset a user's conversation (start fresh)."""
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.info(f"Session cleared for user={user_id}")

    def has_session(self, user_id: str) -> bool:
        return user_id in self._sessions


# ---------------------------------------------------------------------------
# DifyClient
# ---------------------------------------------------------------------------

class DifyClient:
    """
    Async-friendly, streaming-capable client for the Dify Chat-Message API.

    Usage
    -----
    client = DifyClient()

    # Streaming (yields text chunks as they arrive):
    for chunk in client.stream_message(pdf_text, user_id="user_abc"):
        print(chunk, end="", flush=True)

    # Blocking (waits for full response):
    result = client.send_message(pdf_text, user_id="user_abc")
    print(result["answer"])
    """

    # SSE event types emitted by Dify
    _SSE_AGENT_MESSAGE  = "agent_message"
    _SSE_MESSAGE        = "message"
    _SSE_MESSAGE_END    = "message_end"
    _SSE_AGENT_THOUGHT  = "agent_thought"
    _SSE_ERROR          = "error"
    _SSE_PING           = "ping"

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        user_id: str = None,
        timeout: int = 120,
    ):
        self.api_key  = api_key  or os.getenv("DIFY_API_KEY",  "")
        self.base_url = (base_url or os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1")).rstrip("/")
        self.user_id  = user_id  or os.getenv("DIFY_USER_ID",  f"user_{uuid.uuid4().hex[:8]}")
        self.timeout  = timeout

        if not self.api_key:
            raise DifyAuthError(
                "No DIFY_API_KEY provided. Set it in your .env file or pass it "
                "explicitly to DifyClient(api_key=...)."
            )

        self.session_manager = SessionManager()

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        })

        logger.info(f"DifyClient initialised — base_url={self.base_url}, user={self.user_id}")

    # ------------------------------------------------------------------
    # Public: Streaming
    # ------------------------------------------------------------------

    def stream_message(
        self,
        query: str,
        user_id: str = None,
        inputs: dict = None,
        reset_session: bool = False,
    ) -> Generator[str, None, None]:
        """
        Send a message to the Dify agent and yield text chunks as they
        stream back via Server-Sent Events (SSE).

        Yields
        ------
        str
            Incremental text deltas from the agent's response. Includes
            both `agent_message` (ReAct reasoning steps) and `message`
            (final answer) events so the UI can show live progress.

        Raises
        ------
        DifyStreamError
            If the stream contains an error event.
        DifyAuthError
            If the API key is invalid.
        DifyRateLimitError
            If the API rate limit is hit.
        DifyAPIError
            For any other non-2xx response.
        """
        uid = user_id or self.user_id

        if reset_session:
            self.session_manager.clear_session(uid)

        payload = self._build_payload(query, uid, inputs, response_mode="streaming")

        logger.info(f"Streaming request — user={uid}, query_len={len(query)}")

        try:
            with self._session.post(
                f"{self.base_url}/chat-messages",
                json=payload,
                stream=True,
                timeout=self.timeout,
            ) as response:
                self._raise_for_status(response)

                for line in response.iter_lines():
                    if not line:
                        continue

                    decoded = line.decode("utf-8") if isinstance(line, bytes) else line

                    # SSE lines are prefixed with "data: "
                    if not decoded.startswith("data: "):
                        continue

                    raw_json = decoded[len("data: "):]

                    # Skip the "[DONE]" sentinel Dify sometimes sends
                    if raw_json.strip() == "[DONE]":
                        break

                    try:
                        event = json.loads(raw_json)
                    except json.JSONDecodeError:
                        logger.warning(f"Non-JSON SSE line skipped: {raw_json[:120]}")
                        continue

                    event_type = event.get("event", "")

                    # ── Save conversation_id on first event ──────────
                    if conv_id := event.get("conversation_id"):
                        self.session_manager.set_conversation_id(uid, conv_id)

                    # ── Stream agent reasoning steps ─────────────────
                    if event_type == self._SSE_AGENT_THOUGHT:
                        thought = event.get("thought", "")
                        if thought:
                            # Prefix so the UI can style these differently
                            yield f"\n> 🤔 *{thought}*\n"

                    # ── Stream text deltas ───────────────────────────
                    elif event_type in (self._SSE_AGENT_MESSAGE, self._SSE_MESSAGE):
                        delta = event.get("answer", "")
                        if delta:
                            yield delta

                    # ── Stream complete ──────────────────────────────
                    elif event_type == self._SSE_MESSAGE_END:
                        logger.info(f"Stream complete — user={uid}")
                        break

                    # ── Error in stream ──────────────────────────────
                    elif event_type == self._SSE_ERROR:
                        err_msg  = event.get("message", "Unknown stream error")
                        err_code = event.get("code",    "unknown")
                        raise DifyStreamError(
                            f"Stream error from Dify [{err_code}]: {err_msg}"
                        )

                    # ── Keepalive ping — ignore ──────────────────────
                    elif event_type == self._SSE_PING:
                        continue

        except (ConnectionError, Timeout) as exc:
            raise DifyAPIError(
                f"Network error while streaming from Dify: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public: Blocking
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(DifyRateLimitError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def send_message(
        self,
        query: str,
        user_id: str = None,
        inputs: dict = None,
        reset_session: bool = False,
    ) -> dict:
        """
        Send a message and block until the full response is received.

        Retries automatically on rate-limit errors (up to 3 attempts
        with exponential back-off).

        Returns
        -------
        dict
            The full Dify response payload. Key fields:
            - ``answer``          (str)  — The agent's full response text.
            - ``conversation_id`` (str)  — The Dify conversation ID.
            - ``message_id``      (str)  — The unique message ID.
            - ``metadata``        (dict) — Token usage, model info, etc.
        """
        uid = user_id or self.user_id

        if reset_session:
            self.session_manager.clear_session(uid)

        payload = self._build_payload(query, uid, inputs, response_mode="blocking")

        logger.info(f"Blocking request — user={uid}, query_len={len(query)}")

        try:
            response = self._session.post(
                f"{self.base_url}/chat-messages",
                json=payload,
                timeout=self.timeout,
            )
        except (ConnectionError, Timeout) as exc:
            raise DifyAPIError(f"Network error: {exc}") from exc

        self._raise_for_status(response)

        data = response.json()

        # Persist conversation_id for multi-turn support
        if conv_id := data.get("conversation_id"):
            self.session_manager.set_conversation_id(uid, conv_id)

        logger.info(
            f"Blocking response received — "
            f"message_id={data.get('message_id')}, "
            f"tokens={data.get('metadata', {}).get('usage', {}).get('total_tokens', 'n/a')}"
        )

        return data

    # ------------------------------------------------------------------
    # Public: Session utilities
    # ------------------------------------------------------------------

    def reset_session(self, user_id: str = None) -> None:
        """Clear the conversation history for a user (starts a new thread)."""
        self.session_manager.clear_session(user_id or self.user_id)

    def get_conversation_id(self, user_id: str = None) -> Optional[str]:
        """Return the active conversation_id for a user, or None."""
        return self.session_manager.get_conversation_id(user_id or self.user_id)

    # ------------------------------------------------------------------
    # Public: Health check
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """
        Check that the Dify instance is reachable and the API key is valid.

        Returns True on success, False on failure (does not raise).
        """
        try:
            resp = self._session.get(
                f"{self.base_url}/parameters",
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Dify health check passed ✅")
                return True
            logger.warning(f"Dify health check returned {resp.status_code}")
            return False
        except Exception as exc:
            logger.error(f"Dify health check failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        query: str,
        user_id: str,
        inputs: dict,
        response_mode: str,
    ) -> dict:
        """Construct the request payload for the /chat-messages endpoint."""
        payload = {
            "query":         query,
            "user":          user_id,
            "response_mode": response_mode,
            "inputs":        inputs or {},
        }

        # Attach conversation_id if this is a returning session
        conv_id = self.session_manager.get_conversation_id(user_id)
        if conv_id:
            payload["conversation_id"] = conv_id

        return payload

    def _raise_for_status(self, response: requests.Response) -> None:
        """Map HTTP error codes to typed exceptions."""
        if response.status_code == 200:
            return

        raw = None
        try:
            raw = response.text
        except Exception:
            pass

        if response.status_code == 401:
            raise DifyAuthError(
                "Invalid or missing API key. Check DIFY_API_KEY in your .env.",
                status_code=401,
                raw=raw,
            )
        if response.status_code == 403:
            raise DifyAuthError(
                "Access forbidden. Verify the API key has permission for this app.",
                status_code=403,
                raw=raw,
            )
        if response.status_code == 404:
            raise DifyAPIError(
                f"Endpoint not found. Verify DIFY_BASE_URL: {self.base_url}",
                status_code=404,
                raw=raw,
            )
        if response.status_code == 429:
            raise DifyRateLimitError(
                "Rate limit exceeded. The client will retry automatically.",
                status_code=429,
                raw=raw,
            )
        if response.status_code >= 500:
            raise DifyAPIError(
                f"Dify server error ({response.status_code}). Try again shortly.",
                status_code=response.status_code,
                raw=raw,
            )

        # Catch-all for unexpected 4xx
        raise DifyAPIError(
            f"Unexpected response from Dify ({response.status_code}).",
            status_code=response.status_code,
            raw=raw,
        )


# ---------------------------------------------------------------------------
# Module-level singleton (convenience for Streamlit — import and use directly)
# ---------------------------------------------------------------------------

_default_client: Optional[DifyClient] = None


def get_client() -> DifyClient:
    """
    Return the module-level singleton DifyClient, creating it on first call.
    Use this in app.py to avoid re-initialising the client on every rerun.

    Example
    -------
    from dify_client import get_client
    client = get_client()
    for chunk in client.stream_message(pdf_text):
        st.write(chunk)
    """
    global _default_client
    if _default_client is None:
        _default_client = DifyClient()
    return _default_client


# ---------------------------------------------------------------------------
# Quick smoke-test (run directly: python dify_client.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Rissess.AI — DifyClient Smoke Test")
    print("=" * 60)

    try:
        client = DifyClient()
    except DifyAuthError as e:
        print(f"\n❌ Auth error: {e}")
        print("Make sure DIFY_API_KEY is set in your .env file.")
        sys.exit(1)

    print(f"\n📡 Testing connection to: {client.base_url}")
    alive = client.ping()
    print(f"   Health check: {'✅ OK' if alive else '❌ FAILED'}")

    if not alive:
        print("\nCannot reach Dify. Check DIFY_BASE_URL and network access.")
        sys.exit(1)

    test_query = (
        "TEST: Business Name: Acme Corp Ltd. "
        "Loan Request: $500,000. Industry: Import/Export. "
        "Please run a brief risk assessment."
    )

    print(f"\n📤 Sending test query ({len(test_query)} chars)...")
    print("-" * 60)

    try:
        for chunk in client.stream_message(test_query, user_id="smoke_test_user"):
            print(chunk, end="", flush=True)
        print("\n" + "-" * 60)
        print("✅ Streaming test passed.")
        print(f"   Conversation ID: {client.get_conversation_id('smoke_test_user')}")
    except DifyAPIError as e:
        print(f"\n❌ API error: {e}")
        sys.exit(1)
