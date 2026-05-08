import os
import subprocess
import os
import platform
import requests
import time
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
    

def transcribe_audio(file_path: str, output_file: str | None = None) -> str:
    """Transcribe an audio file using AssemblyAI. Accepts a local file path or a web URL.

    If output_file is provided, saves the transcription to that path and returns the full path.
    If output_file is None, returns the full transcription text."""

    api_key = os.environ["ASSEMBLYAI_API_KEY"]

    base_url = "https://api.assemblyai.com"

    headers = {
        "authorization": api_key,
    }

    if os.path.isfile(file_path):
        print(f"[INFO] Uploading local file: {file_path}")

        with open(file_path, "rb") as f:
            upload_response = requests.post(
                base_url + "/v2/upload",
                headers=headers,
                data=f,
            )

        upload_response.raise_for_status()

        audio_url = upload_response.json()["upload_url"]
    else:
        print(f"[INFO] Using audio URL: {file_path}")
        audio_url = file_path

    config = {
        "audio_url": audio_url,
        "speech_models": ["universal-3-pro"],
        "speaker_labels": True,
        "language_detection": True,
        "temperature": 0,
    }

    url = base_url + "/v2/transcript"

    print(f"[INFO] Requesting transcription...")
    response = requests.post(url, json=config, headers=headers)

    if response.status_code != 200:
        try:
            return response.json()['error']
        except Exception:
            return (response.status_code, response.text, response.url)
        
    print(f"[INFO] Transcription requested successfully. Polling for results...")

    transcript_id = response.json()['id']
    polling_endpoint = base_url + "/v2/transcript/" + transcript_id

    while True:
        transcription_result = requests.get(polling_endpoint, headers=headers).json()
        transcription_text = transcription_result['text']

        if transcription_result['status'] == 'completed':
            if output_file is not None:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(transcription_text)

                return os.path.abspath(output_file)
            
            return transcription_text
        elif transcription_result['status'] == 'error':
            return transcription_result['error']

        else:
            time.sleep(3)
