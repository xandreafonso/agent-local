import os
import subprocess
import os
import platform

import dotenv

dotenv.load_dotenv()

# ── Tavily ──────────────────────────────────────────────
from tavily import TavilyClient
from typing import Literal


tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )


def get_system_info() -> str:
    """Get basic system information: OS, hostname, current directory, Python version."""
    return f"""
System: {platform.system()} {platform.release()}

Hostname: {platform.node()}
Current dir: {os.getcwd()}
Python: {platform.python_version()}
User: {os.environ.get('USER', os.environ.get('USERNAME', 'unknown'))}
"""


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
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",  # Evita crash em outputs não-UTF-8 (Windows)
        )
        output = result.stdout.strip()
        if not output:
            output = result.stderr.strip()
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (30s limit)"
    except Exception as e:
        return f"Error executing command: {str(e)}"