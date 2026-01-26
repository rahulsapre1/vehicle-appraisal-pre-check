from __future__ import annotations

import time
from typing import Any

from openai import OpenAI, APIConnectionError, APIStatusError, RateLimitError

from app.settings import get_settings


class LlmClient:
    def __init__(self) -> None:
        settings = get_settings()
        # Configure OpenAI client with retry settings
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            max_retries=3,  # Retry up to 3 times
            timeout=settings.openai_request_timeout_seconds,
        )
        self._settings = settings

    def _make_request_with_retry(self, request_func, max_retries=3) -> dict[str, Any]:
        """
        Make OpenAI request with exponential backoff for rate limits.
        
        Args:
            request_func: Function that makes the OpenAI API call
            max_retries: Maximum number of retries for rate limit errors
            
        Returns:
            Response from OpenAI API
            
        Raises:
            RuntimeError: If request fails after all retries
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                resp = request_func()
                return resp.model_dump()
            except RateLimitError as e:
                last_error = e
                if attempt < max_retries:
                    # Extract wait time from error message or use exponential backoff
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    
                    # Try to parse recommended wait time from error message
                    if hasattr(e, 'message') and 'Please try again in' in str(e.message):
                        try:
                            # Extract wait time like "999ms" or "2s"
                            import re
                            match = re.search(r'try again in (\d+)(ms|s)', str(e.message))
                            if match:
                                value, unit = match.groups()
                                wait_time = int(value) / 1000 if unit == 'ms' else int(value)
                        except:
                            pass  # Use default exponential backoff
                    
                    time.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed
                    raise RuntimeError(
                        f"Rate limit exceeded after {max_retries} retries. "
                        f"Please wait a moment and try again. "
                        f"Error: {e}"
                    ) from e
            except (APIConnectionError, APIStatusError) as e:
                raise RuntimeError(f"API error: {e}") from e
        
        # Should never reach here, but just in case
        raise RuntimeError(f"Request failed: {last_error}") from last_error

    def vision_completion(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        def request():
            return self._client.chat.completions.create(
                model=self._settings.openai_vision_model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        
        try:
            return self._make_request_with_retry(request)
        except RuntimeError as e:
            raise RuntimeError(f"Vision model error: {e}") from e

    def text_completion(self, messages: list[dict[str, Any]], json_mode: bool = True) -> dict[str, Any]:
        def request():
            return self._client.chat.completions.create(
                model=self._settings.openai_text_model,
                messages=messages,
                response_format={"type": "json_object"} if json_mode else None,
            )
        
        try:
            return self._make_request_with_retry(request)
        except RuntimeError as e:
            raise RuntimeError(f"Text model error: {e}") from e


_singleton: LlmClient | None = None


def get_llm_client() -> LlmClient:
    """Get LLM client singleton instance."""
    global _singleton
    if _singleton is None:
        _singleton = LlmClient()
    return _singleton
