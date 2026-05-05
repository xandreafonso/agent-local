# Plano: Agent Command — Administração de Servidores via Terminal

## Visão Geral

Um agente LangChain/LangGraph em **arquivo único** (`agent.py`) que responde a comandos de administração de servidores via terminal. O usuário faz perguntas em linguagem natural e o agente executa comandos shell para responder.

```
$ .venv/Scripts/python agent.py "o que mais está consumindo memória"
$ .venv/Scripts/python agent.py "liste os arquivos desta pasta"
```

## Requisitos Técnicos

- **Python >= 3.10** (LangChain v1 requer)
- **uv** para gestão de dependências
- **Arquivo único**: `agent.py` com tudo
- **Memória**: multi-turn com `InMemorySaver` + `trim_messages`
- **Simplicidade**: mínimo de dependências, código limpo e comentado

## Arquitetura

### Stack Tecnológica

| Componente | Pacote | Versão |
|---|---|---|
| Agente | `langchain` | >=1.0.0 |
| Graph runtime | `langgraph` | >=1.0.0 |
| LLM Provider | `langchain-openai` | >=1.0.0 |
| Tools | `langchain-core` | (transitiva) |

### Graph Architecture (via `create_agent`)

O `create_agent` do LangChain v1 gera automaticamente um StateGraph com este loop:

```
┌──────────────────────────────────────────────┐
│                    Agent                      │
│                                               │
│  User Input ──► Middleware (before_model)     │
│                      │                        │
│                      ▼                        │
│               ┌─────────────┐                 │
│               │   LLM Call   │                │
│               │  (model node)│                │
│               └──────┬──────┘                 │
│                      │                        │
│            ┌─────────▼─────────┐              │
│            │ Tool Call or       │             │
│            │ Final Response?    │             │
│            └───┬───────────┬───┘              │
│                │           │                  │
│         Tool   │           │  Response        │
│                ▼           ▼                  │
│        ┌──────────┐   ┌──────────┐           │
│        │   Tools   │   │   END    │           │
│        │   Node    │   └──────────┘           │
│        └────┬─────┘                           │
│             │                                  │
│             └──► (volta ao LLM com resultado)  │
│                                               │
│  Checkpointer (InMemorySaver) ◄── Persiste    │
│  estado entre turns (via thread_id)            │
└──────────────────────────────────────────────┘
```

### Estratégia de Memória

**Memória de curto prazo** (conversa atual):
- `InMemorySaver` como checkpointer
- `thread_id` distinto por sessão
- Histórico completo preservado entre turns da mesma sessão

**Gestão de contexto** (evitar overflow):
- Middleware `MemoryTrimmer` com hook `before_model`
- Quando `len(messages) > 15`, aplica `trim_messages(max_tokens=3000, strategy="last")`
- `strategy="last"` mantém system prompt + mensagens mais recentes (as mais relevantes)
- `include_system=True` preserva sempre o system prompt

## Ferramentas (Tools)

### 1. `run_shell_command(command: str) -> str`
Executa comandos shell via `subprocess.run()`.
- `shell=True`, `capture_output=True`, `text=True`
- `timeout=30s` para evitar hangs
- `encoding="utf-8"` com `errors="replace"` para Windows
- Segurança: não executa comandos interativos (`vim`, `nano`, etc.)
- Retorna stdout ou stderr

### 2. `list_directory(path: str = ".") -> str`
Lista conteúdos de diretórios com `os.listdir()` ou `os.scandir()`.
- Mostra nome, tamanho, tipo (arquivo/diretório)
- Formatação legível

### 3. `check_system_resources() -> str`
Comando multiplataforma para recursos do sistema:
- Windows: usa `systeminfo`, `tasklist`, `wmic`
- Linux/Mac: usa `free -h`, `top -b -n1`, `df -h`
- Na verdade, pode delegar ao `run_shell_command` com comandos específicos

**Nota**: Simplificar! O agente pode usar `run_shell_command` para tudo. As tools especializadas são sugar syntax.

## Estrutura do Projeto

```
agent-command/
├── .python-version    (gerado por uv init)
├── pyproject.toml     (gerado por uv init + uv add)
├── README.md          (opcional, instruções)
├── agent.py           (TUDO num arquivo)
└── .venv/             (virtual env)
```

## Detalhe do `agent.py`

```python
"""
Agent Command — Server Admin Agent
Uso: .venv/Scripts/python agent.py "sua pergunta aqui"
     .venv/Scripts/python agent.py              (modo interativo)
"""

import sys
import subprocess
import os
import platform
import uuid
from pathlib import Path

# LangChain imports
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import trim_messages
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# ── Tools ──────────────────────────────────────────────

@tool
def run_shell_command(command: str) -> str:
    """Execute a shell command and return its output.
    
    Use this for ANY system administration task:
    - Check memory: 'wmic OS get FreePhysicalMemory' (Windows) or 'free -h' (Linux)
    - List processes: 'tasklist' (Windows) or 'ps aux' (Linux)
    - Check disk: 'wmic logicaldisk get size,freespace' (Windows) or 'df -h' (Linux)
    - List files: 'dir' (Windows) or 'ls -la' (Linux)
    - Network info: 'ipconfig' (Windows) or 'ifconfig' (Linux)
    
    Args:
        command: The shell command to execute.
    """
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=30, encoding="utf-8", errors="replace"
        )
        output = result.stdout.strip()
        if not output:
            output = result.stderr.strip()
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (30s limit)"
    except Exception as e:
        return f"Error executing command: {str(e)}"

@tool
def get_system_info() -> str:
    """Get basic system information: OS, hostname, current directory, Python version."""
    return f"""System: {platform.system()} {platform.release()}
Hostname: {platform.node()}
Current dir: {os.getcwd()}
Python: {platform.python_version()}
User: {os.environ.get('USER', os.environ.get('USERNAME', 'unknown'))}"""

# ── Middleware: Memory Management ──────────────────────

class MemoryTrimmer(AgentMiddleware):
    """Trim conversation history to prevent context overflow."""
    
    def before_model(self, state: AgentState, runtime) -> dict | None:
        messages = state.get("messages", [])
        if len(messages) > 15:
            return {
                "messages": trim_messages(
                    messages,
                    max_tokens=3000,
                    strategy="last",
                    include_system=True,
                    allow_partial=False,
                )
            }
        return None

# ── Agent Factory ──────────────────────────────────────

def create_server_agent():
    """Create the server admin agent with tools and memory."""
    model = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
    )
    
    tools = [run_shell_command, get_system_info]
    
    system_prompt = f"""You are a helpful server administration assistant running on {platform.system()}.

Your job is to help the user manage their system via shell commands.

Guidelines:
- Use `run_shell_command` to execute any system command
- Use `get_system_info` to check the environment
- Always explain what command you're running and why
- If a command fails, try an alternative approach
- Be careful with destructive commands (rm, del, format, etc.) — warn the user first
- Commands should be appropriate for {platform.system()} OS
- Keep responses concise and practical
- Current working directory: {os.getcwd()}
"""
    
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=InMemorySaver(),
        middleware=[MemoryTrimmer()],
    )

# ── Main ───────────────────────────────────────────────

def main():
    # Requer OPENAI_API_KEY no ambiente
    if not os.environ.get("OPENAI_API_KEY"):
        print("Erro: Variável de ambiente OPENAI_API_KEY não definida.")
        print("Defina com: set OPENAI_API_KEY=sk-...   (Windows)")
        print("        ou: export OPENAI_API_KEY=sk-... (Linux/Mac)")
        sys.exit(1)
    
    agent = create_server_agent()
    session_id = str(uuid.uuid4())[:8]
    
    # Modo: argumento único ou interativo
    if len(sys.argv) > 1:
        # Modo single-shot
        prompt = " ".join(sys.argv[1:])
        print(f"🤖 Agent (session: {session_id})")
        print(f"📝 {prompt}\n")
        
        result = agent.invoke(
            {"messages": [{"role": "user", "content": prompt}]},
            {"configurable": {"thread_id": session_id}}
        )
        # Última mensagem (resposta do agente)
        last_msg = result["messages"][-1]
        print(last_msg.content)
    else:
        # Modo interativo (multi-turn)
        print(f"🤖 Server Admin Agent (session: {session_id})")
        print("   Digite 'exit' ou 'quit' para sair\n")
        
        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAté logo!")
                break
            
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("Até logo!")
                break
            
            result = agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]},
                {"configurable": {"thread_id": session_id}}
            )
            last_msg = result["messages"][-1]
            print(f"\n{last_msg.content}\n")

if __name__ == "__main__":
    main()
```

## Setup e Instalação

```bash
# 1. Criar projeto
cd agent-command
uv init

# 2. Adicionar dependências
uv add langchain langgraph langchain-openai

# 3. Criar agent.py (copiar código acima)

# 4. Configurar API key
set OPENAI_API_KEY=sk-...    # Windows
export OPENAI_API_KEY=sk-...  # Linux/Mac

# 5. Testar
.venv/Scripts/python agent.py "liste os arquivos desta pasta"
.venv/Scripts/python agent.py "o que mais está consumindo memória"
.venv/Scripts/python agent.py                        # modo interativo
```

## Pontos de Atenção

1. **Windows vs Linux**: O system prompt já inclui o OS atual. Comandos shell são OS-specific.
2. **Segurança**: O agente tem acesso shell — avisa antes de comandos destrutivos (isso depende do LLM seguir o system prompt).
3. **Timeout**: 30s por comando para evitar hangs.
4. **Encoding**: `errors="replace"` para lidar com saídas não-UTF-8 no Windows.
5. **Custo**: `gpt-4o-mini` é barato (~$0.15/1M tokens). Com trimming, cada turn custa frações de centavo.

## Testes Manuais

```bash
# Teste 1: Listar arquivos
.venv/Scripts/python agent.py "liste os arquivos desta pasta"

# Teste 2: Memória
.venv/Scripts/python agent.py "qual o diretório atual?"
# > resposta...
.venv/Scripts/python agent.py "liste os arquivos daí"  # mesmo thread_id?
# NOTA: single-shot mode usa novo session_id a cada execução
# Para testar memória, usar modo interativo

# Teste 3: Modo interativo multi-turn
.venv/Scripts/python agent.py
> qual o diretório atual?
> liste os arquivos
> qual o maior arquivo?
> exit

# Teste 4: Trimming (fazer 20+ perguntas no modo interativo)
```
