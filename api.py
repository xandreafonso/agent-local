import os
import uuid
import time
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from deepagent import deepagent as agent

load_dotenv()


app = FastAPI()


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]]
    stream: bool = False
    model: str = "deepagent"


def openai_chunk(content: str, finish_reason: str | None = None) -> str:
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "deepagent",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def extract_content(msg: dict) -> str:
    raw = msg.get("content", "")
    if isinstance(raw, str):
        return raw
    return "".join(c if isinstance(c, str) else c.get("text", "") for c in raw)


TOOL_OUTPUT_PREVIEW = int(os.getenv("TOOL_OUTPUT_PREVIEW", 300))


def tool_call_chunk(name: str, inputs: dict) -> str:
    params = json.dumps(inputs, ensure_ascii=False)
    return openai_chunk(f"\n> **{name}**({params})\n")


def tool_result_chunk(output: str) -> str:
    preview = output[:TOOL_OUTPUT_PREVIEW] + ("…" if len(output) > TOOL_OUTPUT_PREVIEW else "")
    return openai_chunk(f"> {preview}\n\n")


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    input_data = {"messages": req.messages}

    if req.stream:
        async def stream():
            async for event in agent.astream_events(input_data, version="v2"):
                if event["event"] == "on_tool_start":
                    yield tool_call_chunk(event.get("name", "tool"), event["data"].get("input", {}))
                elif event["event"] == "on_tool_end":
                    yield tool_result_chunk(str(event["data"].get("output", "")))
                elif event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        yield openai_chunk(text)
            yield openai_chunk("", finish_reason="stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    preamble = ""
    final_content = ""

    async for event in agent.astream_events(input_data, version="v2"):
        if event["event"] == "on_tool_start":
            params = json.dumps(event["data"].get("input", {}), ensure_ascii=False)
            preamble += f"\n> **{event.get('name', 'tool')}**({params})\n"
        elif event["event"] == "on_tool_end":
            output = str(event["data"].get("output", ""))
            preview = output[:TOOL_OUTPUT_PREVIEW] + ("…" if len(output) > TOOL_OUTPUT_PREVIEW else "")
            preamble += f"> {preview}\n\n"
        elif event["event"] == "on_chain_end" and "messages" in (event["data"].get("output") or {}):
            messages = event["data"]["output"]["messages"]
            last = next((m for m in reversed(messages) if getattr(m, "type", None) == "ai"), None)
            if last:
                final_content = extract_content(last.__dict__)

    content = preamble + final_content

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "deepagent",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
