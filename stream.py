import os
import sys
import uuid
from pathlib import Path

# ── LangChain / LangGraph ──────────────────────────────
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

# ── LangChain / Deepagents ──────────────────────────────
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend

# ── Dotenv ──────────────────────────────────────────────
from dotenv import load_dotenv

from model import resolve_model
from tools import get_system_info, run_shell_command

load_dotenv()

sys.stdout.reconfigure(encoding='utf-8')

# ─── Rich / prompt_toolkit ─────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.markdown import Markdown
from rich.status import Status
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.styles import Style

console = Console(highlight=False)
_input_style = Style.from_dict({"": "cyan"})


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════

def _print_tool_call(name: str, args: dict) -> None:
    args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items()) if args else ""
    console.print(f"  [bold yellow]⚙[/bold yellow]  [yellow]{name}[/yellow]([dim]{args_str}[/dim])")


def _print_tool_result(name: str, content: str) -> None:
    preview = content.strip()

    if len(preview) > 500:
        preview = preview[:500] + "[dim]…[/dim]"

    console.print(f"  [bold green]✓[/bold green]  [green]{name}[/green]\n[dim]{preview}[/dim]")


def _stream_response(agent, user_input: str, session_id: str) -> tuple[int, int, int]:
    spinner = Status("[dim]Agente pensando...[/dim]", console=console, spinner="dots")
    spinner.start()
    spinner_active = True
    tokens_in = tokens_out = tokens_reasoning = 0

    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        {"configurable": {"thread_id": session_id}, "recursion_limit": 90},
        reasoning=True,
        stream_mode=["updates"],
        subgraphs=True,
        version="v2",
    ):
        if chunk["type"] == "updates":
            data = chunk["data"]

            if "model" in data:
                for msg in data["model"].get("messages", []):
                    if isinstance(msg, AIMessage):
                        # Format 1: ChatOpenRouter / DeepSeek R1 style
                        reasoning = msg.additional_kwargs.get("reasoning_content") or ""

                        if not reasoning and isinstance(msg.content, list):
                            parts = []
                            for b in msg.content:
                                if not isinstance(b, dict):
                                    continue
                                if b.get("type") == "thinking":
                                    # Format 2: Anthropic extended thinking
                                    parts.append(b.get("thinking", ""))
                                elif b.get("type") == "reasoning":
                                    # Format 3: OpenAI Responses API (kimi-k2, mimo, etc.)
                                    for item in b.get("content", []):
                                        if isinstance(item, dict) and item.get("type") == "reasoning_text":
                                            parts.append(item.get("text", ""))
                            reasoning = "\n".join(p for p in parts if p)

                        text = (
                            "\n".join(
                                b.get("text", "") for b in msg.content
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                            if isinstance(msg.content, list)
                            else str(msg.content)
                        )

                        if reasoning or text or msg.tool_calls:
                            if spinner_active:
                                spinner.stop()
                                spinner_active = False

                        if reasoning:
                            console.print(Markdown(reasoning), style="dim")
                            console.line()

                        if text:
                            console.print(Markdown(text))

                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                _print_tool_call(tc["name"], tc.get("args", {}))
                                
                        if msg.usage_metadata:
                            tokens_in += msg.usage_metadata.get("input_tokens", 0)
                            tokens_out += msg.usage_metadata.get("output_tokens", 0)
                            tokens_reasoning += msg.usage_metadata.get("reasoning_tokens", 0)

            elif "tools" in data:
                for msg in data["tools"].get("messages", []):
                    if isinstance(msg, ToolMessage):
                        if spinner_active:
                            spinner.stop()
                            spinner_active = False

                        _print_tool_result(msg.name, str(msg.content))

    if spinner_active:
        spinner.stop()

    return tokens_in, tokens_out, tokens_reasoning


def main():
    console.print("[dim]Inicializando agente...[/dim]", end=" ")  
    max_tk = 12192  
    model, provider, model_id = resolve_model(max_tokens=max_tk, reasoning_level="medium")

    tools = [get_system_info, run_shell_command]

    agent = create_deep_agent(
            model=model,
            tools=tools,
            checkpointer=InMemorySaver(),
            backend=LocalShellBackend(virtual_mode=False, root_dir="/"),
            skills=[
                Path(os.path.join(Path.home(), ".agent-local", "skills")).as_posix()[2:],
                Path(os.path.join(os.getcwd(), "skills")).as_posix()[2:]
            ],
            memory=[
                Path(os.path.join(Path.home(), ".agent-local", "AGENTS.md")).as_posix()[2:],
                Path(os.path.join(os.getcwd(), "AGENTS.md")).as_posix()[2:]
            ],
        )
    
    console.print("[dim]pronto.[/dim]")

    session_id = str(uuid.uuid4())[:8]

    # ── Modo: Single-shot (com argumento) ───────────────
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        
        console.print(Panel(
            f"[bold]{prompt}[/bold]",
            title=f"[cyan]{provider}/{model_id} (max. tk: {max_tk})[/cyan]  [dim]#{session_id}[/dim]",
            border_style="cyan",
        ))

        console.print()

        t_in, t_out, t_r = _stream_response(agent, prompt, session_id)
        if t_in or t_out or t_r:
            console.print(f"[dim]tokens — entrada: {t_in}  saída: {t_out}  reasoning: {t_r}[/dim]")

    # ── Modo: Interativo (sem argumentos) ───────────────
    else:
        console.print(Panel(
            f"[bold cyan]Server Admin Agent[/bold cyan]\n"
            f"[dim]session [bold]#{session_id}[/bold]  ·  {provider}/{model_id} (max. tk: {max_tk})[/dim]\n"
            f"[dim]'exit' ou 'quit' para sair[/dim]",
            border_style="cyan",
            expand=False,
        ))

        console.print()

        total_in = total_out = total_r = 0

        while True:
            try:
                user_input = pt_prompt("> ", style=_input_style).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Até logo![/dim]")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                console.print("[dim]Até logo![/dim]")
                break

            console.print()

            t_in, t_out, t_r = _stream_response(agent, user_input, session_id)
            total_in += t_in
            total_out += t_out
            total_r += t_r

            if t_in or t_out or t_r:
                console.print(
                    f"[dim]tokens  turno — entrada: {t_in}  saída: {t_out}  reasoning: {t_r}"
                    f"   │   sessão — entrada: {total_in}  saída: {total_out}  reasoning: {total_r}[/dim]"
                )

            console.print(Rule(style="dim"))


if __name__ == "__main__":
    main()
