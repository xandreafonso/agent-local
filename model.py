import os
import sys
from pathlib import Path
from deepagents import create_deep_agent
from tools import run_shell_command, get_system_info
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_deepseek import ChatDeepSeek
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend, LocalShellBackend

import dotenv

dotenv.load_dotenv()

def resolve_model(command_model: str | None = None):
    if command_model:
        spec = command_model
    else:
        spec = os.environ.get("AGENT_COMMAND_MODEL", "openai/gpt-5.2")

    try:
        provider, model_id = spec.split("/", 1)
    except ValueError:
        print(f"[ERRO] Formato inválido: '{spec}'. Use: provider/model-id")
        sys.exit(1)

    # Provider → (api_key_env, base_url ou None)
    PROVIDERS: dict[str, tuple[str, str | None]] = {
        "anthropic": ("ANTHROPIC_API_KEY",  None),
        "openai":    ("OPENAI_API_KEY",     None),
        "zai":     ("ZAI_API_KEY",      "https://api.z.ai/api/coding/paas/v4"),
        "deepseek":  ("DEEPSEEK_API_KEY",   "https://api.deepseek.com/v1"),
        "minimax":  ("MINIMAX_API_KEY",   "https://api.minimax.io/anthropic"),
        "alibaba":  ("DASHSCOPE_API_KEY",   "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        "xandre":   ("XANDRE_MODEL",       "http://localhost:8000/v1"),
    }

    if provider in PROVIDERS:
        key_env, base_url = PROVIDERS[provider]

        api_key = os.environ.get(key_env)

        if not api_key:
            print(f"[ERRO] {key_env} não definida no .env para o provider '{provider}'")
            sys.exit(1)

        if provider == "anthropic":
            model = ChatAnthropic(model=model_id, temperature=0, api_key=api_key)
        elif provider == "minimax":
            model = ChatAnthropic(model=model_id, temperature=0, api_key=api_key, base_url=base_url)
        elif provider == "deepseek":
            model = ChatDeepSeek(model=model_id, temperature=0, api_key=api_key, base_url=base_url)
        else:
            kwargs = {"model": model_id, "temperature": 0, "api_key": api_key}

            if base_url:
                kwargs["base_url"] = base_url

            model = ChatOpenAI(**kwargs)
    else:
        api_key = os.environ.get("OPENROUTER_API_KEY")

        if not api_key:
            print(f"[ERRO] Provider '{provider}' desconhecido e OPENROUTER_API_KEY não definida")
            sys.exit(1)

        model = ChatOpenAI(
            model=f"{provider}/{model_id}",
            temperature=0,
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        print(f"[INFO] Provider '{provider}' → OpenRouter (fallback)")

    return model, provider, model_id