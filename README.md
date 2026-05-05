# Agent Command

Agente de administração de servidores via linguagem natural. Executa comandos shell, lê ficheiros e responde a perguntas sobre o sistema.

## Requisitos

- Python >= 3.12
- [`uv`](https://docs.astral.sh/uv/) instalado
- Chave de API de pelo menos um provider

## Instalação

```bash
uv sync
```

Configurar variáveis de ambiente:

```bash
cp .env .env.local   # ou edita o .env diretamente
```

## Configuração

| Variável | Descrição | Default |
|---|---|---|
| `AGENT_COMMAND_MODEL` | Provider e modelo (`provider/model-id`) | `openai/gpt-5.2` |
| `ANTHROPIC_API_KEY` | Chave da Anthropic | — |
| `OPENAI_API_KEY` | Chave da OpenAI | — |
| `DEEPSEEK_API_KEY` | Chave da DeepSeek | — |
| `ZAI_API_KEY` | Chave da Z.ai | — |
| `MINIMAX_API_KEY` | Chave da MiniMax | — |
| `DASHSCOPE_API_KEY` | Chave da Alibaba (Qwen) | — |
| `OPENROUTER_API_KEY` | Chave do OpenRouter (fallback) | — |

### Multi-Model

Define `AGENT_COMMAND_MODEL=provider/model-id` no `.env`:

| Provider | Exemplo |
|---|---|
| `openai` | `openai/gpt-5.2` |
| `anthropic` | `anthropic/claude-sonnet-4-6` |
| `deepseek` | `deepseek/deepseek-v4-pro` |
| `zai` | `zai/glm-5.1` |
| `minimax` | `minimax/MiniMax-M2.7` |
| `alibaba` | `alibaba/qwen-plus` |
| `xandre` | `xandre/<model>` (servidor local em `localhost:8000`) |
| **qualquer outro** | `moonshotai/kimi-k2.6` → OpenRouter como fallback |

---

## stream.py — Agente de linha de comandos

Interface de terminal com output rico (markdown, tool calls, contagem de tokens).

### Modo interativo

```bash
.venv/Scripts/python stream.py
```

Inicia uma sessão com memória entre turnos. Escreve `exit` ou `quit` para sair.

```
> qual o diretório atual?
> lista os ficheiros
> qual o maior?
> exit
```

### Modo single-shot

Passa a pergunta diretamente como argumento:

```bash
.venv/Scripts/python stream.py "o que mais está a consumir memória?"
.venv/Scripts/python stream.py "lista os ficheiros desta pasta"
.venv/Scripts/python stream.py "quanto espaço em disco está livre?"
```

---

## deepagent.py — Servidor LangGraph

Expõe o agente como um grafo LangGraph, utilizável via `langgraph dev` (UI de desenvolvimento) ou integrado noutra aplicação.

### Iniciar o servidor de desenvolvimento

```bash
.venv/Scripts/langgraph dev
```

Abre a UI do LangGraph Studio em `http://localhost:2024` onde podes enviar mensagens e inspecionar o estado do grafo.

O grafo está definido em [langgraph.json](langgraph.json) e aponta para `deepagent.py:deepagent`.

---

## api.py — API compatível com OpenAI

Servidor FastAPI que expõe o agente com a interface `/v1/chat/completions` do OpenAI, permitindo ligar qualquer cliente ou ferramenta que suporte a API da OpenAI (Cursor, Open WebUI, etc.).

### Iniciar o servidor

```bash
.venv/Scripts/uvicorn api:app --port 8000 --reload
```

### Endpoints

| Método | Path | Descrição |
|---|---|---|
| `POST` | `/v1/chat/completions` | Chat com o agente |

Suporta `"stream": true` para respostas em streaming (SSE).

### Exemplo de pedido

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepagent",
    "messages": [{"role": "user", "content": "lista os ficheiros desta pasta"}],
    "stream": false
  }'
```

### Ligar como provider local (ex: Cursor)

Configura o base URL como `http://localhost:8000/v1` e qualquer API key (não é validada). O modelo pode ser qualquer string — o agente ignora-a.

### Variável de ambiente

| Variável | Descrição | Default |
|---|---|---|
| `TOOL_OUTPUT_PREVIEW` | Nº de caracteres do output de tools a incluir na resposta | `300` |

---

## Arquitectura

```
stream.py        ← CLI (rich + prompt_toolkit)
deepagent.py     ← grafo LangGraph (usado pelo langgraph dev e pela api.py)
api.py           ← servidor FastAPI (OpenAI-compatible)
model.py         ← resolve o modelo a partir de AGENT_COMMAND_MODEL
tools.py         ← run_shell_command, get_system_info
```
