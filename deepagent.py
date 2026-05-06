import os
from pathlib import Path
from deepagents import create_deep_agent
from model import resolve_model
from tools import run_shell_command, get_system_info
from deepagents.backends import LocalShellBackend

import dotenv

dotenv.load_dotenv()

model, provider, model_id = resolve_model()

tools = [get_system_info, run_shell_command]

deepagent = create_deep_agent(
        model=model,
        tools=tools,
        backend=LocalShellBackend(virtual_mode=False, root_dir="/"),
        memory=[
            Path(os.path.join(Path.home(), ".agent-local", "AGENTS.md")).as_posix()[2:],
            Path(os.path.join(os.getcwd(), "AGENTS.md")).as_posix()[2:]
        ],
    )