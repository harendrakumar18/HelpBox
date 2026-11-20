import logging
from abc import ABC, abstractmethod
from typing import Iterator, List, Optional
from langchain_core.messages import BaseMessage

from app import config

logger = logging.getLogger("helpbox.llm")


class BaseLLMProvider(ABC):
    """Abstract interface for LLM answer generation in Helpbox."""

    @abstractmethod
    def generate(self, messages: List[BaseMessage]) -> str:
        """Synchronously generate an answer from a list of messages."""
        pass

    @abstractmethod
    def stream(self, messages: List[BaseMessage]) -> Iterator[str]:
        """Stream generated text chunks in real time."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass


class OllamaProvider(BaseLLMProvider):
    """
    Default local development LLM provider using Ollama.
    Runs Qwen 3.5 2B Q4_K_M entirely offline on CPU with conservative 4K context.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        context_window: Optional[int] = None,
        num_predict: Optional[int] = None,
        keep_alive: Optional[str] = None,
    ):
        from langchain_ollama import ChatOllama

        self._model = model or config.OLLAMA_MODEL
        self._base_url = base_url or config.OLLAMA_BASE_URL
        self._num_ctx = context_window or config.OLLAMA_CONTEXT_WINDOW
        self._num_predict = num_predict or getattr(config, "OLLAMA_NUM_PREDICT", 196)
        self._keep_alive = keep_alive or getattr(config, "OLLAMA_KEEP_ALIVE", "60m")

        self._llm = ChatOllama(
            model=self._model,
            base_url=self._base_url,
            reasoning=False,  # Disable chain-of-thought to stream concise grounded clinical answers
            temperature=0.1,
            num_ctx=self._num_ctx,
            num_predict=self._num_predict,
            keep_alive=self._keep_alive,
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, messages: List[BaseMessage]) -> str:
        response = self._llm.invoke(messages)
        return str(response.content)

    def stream(self, messages: List[BaseMessage]) -> Iterator[str]:
        for chunk in self._llm.stream(messages):
            if chunk.content:
                yield str(chunk.content)


class GeminiProvider(BaseLLMProvider):
    """
    Optional cloud LLM provider using official Google GenAI integration.
    Active only when the user provides GEMINI_API_KEY in .env or Codespaces Secrets.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        from langchain_google_genai import ChatGoogleGenerativeAI

        self._api_key = api_key or config.GEMINI_API_KEY
        if not self._api_key:
            raise ValueError(
                "Gemini provider selected but GEMINI_API_KEY is not configured. "
                "Add GEMINI_API_KEY to your environment or switch to GENERATION_PROVIDER=ollama."
            )

        self._model = model or config.GEMINI_MODEL
        self._llm = ChatGoogleGenerativeAI(
            model=self._model,
            google_api_key=self._api_key,
            temperature=0.1,
        )

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, messages: List[BaseMessage]) -> str:
        response = self._llm.invoke(messages)
        return str(response.content)

    def stream(self, messages: List[BaseMessage]) -> Iterator[str]:
        for chunk in self._llm.stream(messages):
            if chunk.content:
                yield str(chunk.content)


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    Optional private company endpoint adapter (e.g. company vLLM/TGI inference cluster).
    Requires zero OpenAI account, OpenAI key, or OpenAI billing.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self._base_url = base_url or config.OPENAI_COMPATIBLE_BASE_URL
        if not self._base_url:
            raise ValueError("OPENAI_COMPATIBLE_BASE_URL is required for OpenAI-compatible provider.")

        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError("langchain-openai is required for OpenAI-compatible endpoints.")

        self._model = model or config.OPENAI_COMPATIBLE_MODEL
        self._api_key = api_key or config.OPENAI_COMPATIBLE_API_KEY

        self._llm = ChatOpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            model=self._model,
            temperature=0.1,
        )

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, messages: List[BaseMessage]) -> str:
        response = self._llm.invoke(messages)
        return str(response.content)

    def stream(self, messages: List[BaseMessage]) -> Iterator[str]:
        for chunk in self._llm.stream(messages):
            if chunk.content:
                yield str(chunk.content)


_provider_cache: dict[str, BaseLLMProvider] = {}


def reset_provider_cache() -> None:
    """Clear cached LLM provider instances (useful for testing or config reloads)."""
    global _provider_cache
    _provider_cache.clear()


def get_llm_provider(name: Optional[str] = None) -> BaseLLMProvider:
    """Factory to instantiate and reuse the configured generation provider."""
    global _provider_cache
    provider_name = (name or config.GENERATION_PROVIDER).strip().lower()

    if provider_name in _provider_cache:
        return _provider_cache[provider_name]

    if provider_name == "ollama":
        provider = OllamaProvider()
    elif provider_name == "gemini":
        provider = GeminiProvider()
    elif provider_name in ("openai_compatible", "company_endpoint"):
        provider = OpenAICompatibleProvider()
    else:
        raise ValueError(f"Unknown generation provider '{provider_name}'. Supported: ollama, gemini, openai_compatible")

    _provider_cache[provider_name] = provider
    return provider
