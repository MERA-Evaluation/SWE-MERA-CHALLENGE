"""A small ReAct-style Harbor agent with a single bash tool.

The agent runs in Harbor's host process. Model requests therefore go directly
from the host to the configured OpenAI-compatible endpoint, while bash commands
are executed by Harbor inside the task environment.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, override

import httpx

from harbor.agents.base import BaseAgent
from harbor.agents.model_connection import ModelConnectionSpec
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


SYSTEM_PROMPT = """You are an autonomous software-engineering agent.

The repository is available at /testbed. Solve the user's issue by inspecting
the repository, editing the implementation, and running relevant tests. Work
directly on the repository; do not merely describe a possible solution and do
not ask the user to perform steps for you.

You have exactly one tool: bash. Use it for every interaction with the
repository. Make the smallest correct change, preserve existing conventions,
do not modify tests unless the task explicitly requires it, and avoid creating
backup or temporary files in the repository. Before finishing, inspect the
diff and run the most relevant tests you can.

On every working turn, reason briefly and then make exactly one bash tool call.
Do not repeat a command when its previous result is already available. When the
task is complete, make one final bash tool call containing exactly this command:

echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT

Do not combine that command with any other command. It is the only completion
signal; do not finish with a text-only response.
"""

SUBMIT_COMMAND = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"

BASH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Run one bash command in /testbed. Use it to inspect files, edit the "
            "repository, run tests, and inspect git diff."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute.",
                }
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}


def _positive_int(value: int | str, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str | None, limit: int) -> str:
    value = text or ""
    if len(value) <= limit:
        return value
    head = limit // 2
    tail = limit - head
    omitted = len(value) - limit
    return f"{value[:head]}\n... [{omitted} characters omitted] ...\n{value[-tail:]}"


class ReactBashAgent(BaseAgent):
    """Minimal chat-completions ReAct loop with only a bash function tool."""

    MODEL_CONNECTION = ModelConnectionSpec(
        api_key_envs=("REACT_AGENT_API_KEY",),
        base_url_envs=("REACT_AGENT_BASE_URL",),
        passthrough=True,
    )

    def __init__(
        self,
        max_steps: int | str = 120,
        max_tokens: int | str = 4096,
        command_timeout_sec: int | str = 180,
        request_timeout_sec: int | str = 600,
        max_tool_output_chars: int | str = 10000,
        keep_full_tool_outputs: int | str = 4,
        max_history_steps: int | str = 8,
        workdir: str = "/testbed",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.max_steps = _positive_int(max_steps, "max_steps")
        self.max_tokens = _positive_int(max_tokens, "max_tokens")
        self.command_timeout_sec = _positive_int(
            command_timeout_sec, "command_timeout_sec"
        )
        self.request_timeout_sec = _positive_int(
            request_timeout_sec, "request_timeout_sec"
        )
        self.max_tool_output_chars = _positive_int(
            max_tool_output_chars, "max_tool_output_chars"
        )
        self.keep_full_tool_outputs = _positive_int(
            keep_full_tool_outputs, "keep_full_tool_outputs"
        )
        self.max_history_steps = _positive_int(
            max_history_steps, "max_history_steps"
        )
        self.workdir = workdir

    @staticmethod
    @override
    def name() -> str:
        return "react-bash-agent"

    @override
    def version(self) -> str:
        return "0.2.0"

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        # The implementation runs in Harbor's host process and uses only
        # dependencies already pinned by this repository.
        return None

    def _api_model_name(self) -> str:
        if not self.model_name:
            raise ValueError("A model must be supplied with --model")
        if "/" in self.model_name:
            return self.model_name.split("/", 1)[1]
        return self.model_name

    def _request_messages(
        self,
        messages: list[dict[str, Any]],
        history_steps: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return a bounded, protocol-valid suffix of the ReAct conversation."""
        history_limit = history_steps or self.max_history_steps
        prefix = [dict(message) for message in messages[:2]]
        chunks: list[list[dict[str, Any]]] = []
        for message in messages[2:]:
            copied = dict(message)
            if copied.get("role") == "assistant":
                chunks.append([copied])
            elif chunks:
                chunks[-1].append(copied)
            else:
                prefix.append(copied)

        selected_chunks = chunks[-history_limit:]
        compacted = prefix
        if len(selected_chunks) < len(chunks):
            omission_note = (
                "\n\nEarlier working turns were omitted to stay within the "
                "model context limit. The filesystem contains their effects. "
                "Inspect the current repository state and continue; do not "
                "restart the task from scratch."
            )
            compacted[0]["content"] = (
                str(compacted[0].get("content") or "") + omission_note
            )
        for chunk in selected_chunks:
            compacted.extend(chunk)

        tool_indexes = [
            index
            for index, message in enumerate(compacted)
            if message.get("role") == "tool"
        ]
        old_indexes = tool_indexes[: -self.keep_full_tool_outputs]
        for index in old_indexes:
            content = str(compacted[index].get("content") or "")
            compacted[index]["content"] = _truncate(content, 800)

        for message in compacted:
            if message.get("role") != "assistant":
                continue
            if message.get("content") is not None:
                message["content"] = _truncate(str(message["content"]), 2000)
            for key in ("reasoning_content", "reasoning"):
                if message.get(key) is not None:
                    message[key] = _truncate(str(message[key]), 3000)
            bounded_calls = []
            for tool_call in message.get("tool_calls") or []:
                bounded_call = dict(tool_call)
                function = dict(bounded_call.get("function") or {})
                raw_arguments = function.get("arguments")
                if isinstance(raw_arguments, str):
                    try:
                        arguments = json.loads(raw_arguments)
                    except json.JSONDecodeError:
                        arguments = None
                    if isinstance(arguments, dict) and isinstance(
                        arguments.get("command"), str
                    ):
                        arguments["command"] = _truncate(
                            arguments["command"], 4000
                        )
                        function["arguments"] = json.dumps(
                            arguments, ensure_ascii=False
                        )
                bounded_call["function"] = function
                bounded_calls.append(bounded_call)
            if bounded_calls:
                message["tool_calls"] = bounded_calls
        return compacted

    async def _chat_completion(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        api_key: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self.session_id:
            headers["X-Session-ID"] = self.session_id

        last_error: Exception | None = None
        history_steps = self.max_history_steps
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            payload = {
                "model": self._api_model_name(),
                "messages": self._request_messages(messages, history_steps),
                "tools": [BASH_TOOL],
                "tool_choice": "auto",
                "temperature": 0,
                "max_tokens": self.max_tokens,
            }
            try:
                response = await client.post(endpoint, headers=headers, json=payload)
                if response.status_code < 400:
                    return response.json()
                detail = _truncate(response.text, 4000)
                error = RuntimeError(
                    f"LLM returned HTTP {response.status_code}: {detail}"
                )
                context_too_long = response.status_code == 400 and (
                    "maximum context length" in response.text.lower()
                    or "context length" in response.text.lower()
                )
                if context_too_long and history_steps > 1:
                    history_steps = max(1, history_steps // 2)
                    last_error = error
                    continue
                if response.status_code not in {408, 409, 429} and not (
                    500 <= response.status_code < 600
                ):
                    raise error
                last_error = error
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc

            if attempt < max_attempts:
                await asyncio.sleep(2 ** (attempt - 1))

        raise RuntimeError(
            f"LLM request failed after {max_attempts} attempts: {last_error}"
        )

    def _save_trajectory(self, trajectory: dict[str, Any]) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        target = self.logs_dir / "react-bash-trajectory.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(trajectory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(target)

    @staticmethod
    def _usage(response: dict[str, Any]) -> tuple[int, int, int]:
        usage = response.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        prompt_details = usage.get("prompt_tokens_details") or {}
        cached_tokens = int(prompt_details.get("cached_tokens") or 0)
        return prompt_tokens, completion_tokens, cached_tokens

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        access = self.model_connection
        if not access.base_url:
            raise ValueError(
                "No model endpoint configured. Set REACT_AGENT_BASE_URL or "
                "OPENAI_BASE_URL."
            )
        if not access.api_key:
            raise ValueError(
                "No API key configured. Set REACT_AGENT_API_KEY or OPENAI_API_KEY "
                "(use 'dummy' for a local vLLM server)."
            )

        endpoint = f"{access.base_url.rstrip('/')}/chat/completions"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]
        trajectory: dict[str, Any] = {
            "agent": self.name(),
            "version": self.version(),
            "model": self._api_model_name(),
            "endpoint": access.base_url,
            "started_at": _utc_now(),
            "max_steps": self.max_steps,
            "messages": messages.copy(),
            "steps": [],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
            },
            "stop_reason": None,
        }

        timeout = httpx.Timeout(float(self.request_timeout_sec), connect=30.0)
        final_answer = ""
        last_command: str | None = None
        repeat_streak = 0

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for step_number in range(1, self.max_steps + 1):
                    response = await self._chat_completion(
                        client,
                        endpoint,
                        access.api_key,
                        messages,
                    )
                    prompt_tokens, completion_tokens, cached_tokens = self._usage(
                        response
                    )
                    trajectory["usage"]["prompt_tokens"] += prompt_tokens
                    trajectory["usage"]["completion_tokens"] += completion_tokens
                    trajectory["usage"]["cached_tokens"] += cached_tokens

                    choices = response.get("choices") or []
                    if not choices:
                        raise RuntimeError("LLM response contains no choices")

                    choice = choices[0]
                    raw_message = choice.get("message") or {}
                    reasoning_content = (
                        raw_message.get("reasoning_content")
                        or raw_message.get("reasoning")
                    )
                    assistant_message: dict[str, Any] = {
                        "role": "assistant",
                        "content": raw_message.get("content"),
                    }
                    if reasoning_content:
                        # vLLM returns this as `reasoning`; its chat template reads
                        # the normalized OpenAI-compatible `reasoning_content` field
                        # on the next request. Without it, the model loses its plan
                        # after every tool call and repeatedly starts from scratch.
                        assistant_message["reasoning_content"] = reasoning_content
                    tool_calls = raw_message.get("tool_calls") or []
                    if tool_calls:
                        assistant_message["tool_calls"] = tool_calls
                    messages.append(assistant_message)
                    trajectory["messages"].append(
                        {
                            **assistant_message,
                            "finish_reason": choice.get("finish_reason"),
                        }
                    )

                    step_record: dict[str, Any] = {
                        "step": step_number,
                        "timestamp": _utc_now(),
                        "assistant": trajectory["messages"][-1],
                        "tool_results": [],
                    }
                    trajectory["steps"].append(step_record)

                    if not tool_calls:
                        finish_reason = str(choice.get("finish_reason") or "")
                        correction = {
                            "role": "user",
                            "content": (
                                "Your previous response did not contain a bash tool "
                                f"call (finish_reason={finish_reason!r}). Continue "
                                "concisely with exactly one bash tool call. If the "
                                f"task is complete, call `{SUBMIT_COMMAND}` exactly."
                            ),
                        }
                        messages.append(correction)
                        trajectory["messages"].append(correction)
                        step_record["format_error"] = "missing_tool_call"
                        self._save_trajectory(trajectory)
                        continue

                    submitted = False
                    for tool_call in tool_calls:
                        tool_call_id = str(tool_call.get("id") or "missing-id")
                        function = tool_call.get("function") or {}
                        function_name = str(function.get("name") or "")
                        raw_arguments = function.get("arguments") or "{}"
                        try:
                            arguments = (
                                json.loads(raw_arguments)
                                if isinstance(raw_arguments, str)
                                else raw_arguments
                            )
                        except (json.JSONDecodeError, TypeError):
                            arguments = {}

                        command = (
                            arguments.get("command")
                            if isinstance(arguments, dict)
                            else None
                        )
                        if function_name != "bash":
                            tool_output = (
                                f"Tool error: unknown tool {function_name!r}; only "
                                "the bash tool is available."
                            )
                        elif not isinstance(command, str) or not command.strip():
                            tool_output = "Tool error: bash requires a non-empty command."
                        else:
                            normalized_command = command.strip()
                            is_submit = (
                                len(tool_calls) == 1
                                and normalized_command == SUBMIT_COMMAND
                            )
                            if (
                                normalized_command == last_command
                                and not is_submit
                            ):
                                repeat_streak += 1
                                tool_output = (
                                    "Tool call skipped: this is the same command as "
                                    "the immediately preceding command, whose result "
                                    "is already in the conversation. Use that result "
                                    "and take a different action."
                                )
                            else:
                                repeat_streak = 0
                                try:
                                    result = await environment.exec(
                                        command=command,
                                        cwd=self.workdir,
                                        timeout_sec=self.command_timeout_sec,
                                    )
                                    tool_output = _truncate(
                                        f"exit_code: {result.return_code}\n"
                                        f"stdout:\n{result.stdout or ''}\n"
                                        f"stderr:\n{result.stderr or ''}",
                                        self.max_tool_output_chars,
                                    )
                                except Exception as exc:
                                    tool_output = (
                                        "Tool execution error: "
                                        f"{type(exc).__name__}: {exc}"
                                    )
                            last_command = normalized_command
                            submitted = submitted or is_submit

                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": function_name or "bash",
                            "content": tool_output,
                        }
                        messages.append(tool_message)
                        trajectory["messages"].append(tool_message)
                        step_record["tool_results"].append(tool_message)

                    self._save_trajectory(trajectory)
                    if submitted:
                        final_answer = str(
                            raw_message.get("content") or reasoning_content or ""
                        )
                        trajectory["stop_reason"] = "submitted"
                        self._save_trajectory(trajectory)
                        return

                trajectory["stop_reason"] = "max_steps"
        except Exception as exc:
            trajectory["stop_reason"] = "error"
            trajectory["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            trajectory["finished_at"] = _utc_now()
            self._save_trajectory(trajectory)
            usage = trajectory["usage"]
            context.n_input_tokens = usage["prompt_tokens"]
            context.n_output_tokens = usage["completion_tokens"]
            context.n_cache_tokens = usage["cached_tokens"]
            context.cost_usd = 0.0
            context.metadata = {
                "steps": len(trajectory["steps"]),
                "stop_reason": trajectory["stop_reason"],
                "final_answer": _truncate(final_answer, 4000),
            }
