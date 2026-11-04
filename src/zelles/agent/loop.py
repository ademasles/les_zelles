"""A small, provider-agnostic agent loop over the tool registry.

Each step the model returns one JSON action (validated with Pydantic): call a
tool, or give the final answer. This works with any model that can produce
JSON, including 7-14B local models, which native function calling does not
always cover. The full trace (actions, observations, tokens) is returned for
debugging and evaluation.
"""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, Field

from zelles.agent.tools import ToolContext, ToolError, ToolRegistry
from zelles.domain.spec import Usage
from zelles.llm.base import LLM, LLMError, Message

AGENT_SYSTEM = """\
You are an assistant for joinery estimators working on French tender specifications \
(CCTP). You answer by using tools that read analysed CCTPs: search passages, read \
requirements, walk the knowledge graph, check products, find conflicts.

Work step by step. At each step reply with one JSON object:
{{"thought": "<one short sentence>", "action": "<tool name or final_answer>", \
"arguments": {{...}}, "answer": "<only with final_answer>"}}

Rules:
- Ground every claim in tool results and cite passage ids like [c0012].
- Prefer get_requirements and the graph for structured facts, search_passages for wording.
- Stop as soon as you can answer. If the documents do not say, say so.
- Answer in the language of the question.

Tools:
{tools}
"""

MAX_OBSERVATION_CHARS = 6000


class AgentAction(BaseModel):
    thought: str = ""
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = None


class TraceStep(BaseModel):
    action: str
    arguments: dict[str, Any]
    thought: str = ""
    observation: str | None = None
    error: str | None = None
    seconds: float = 0.0


class AgentResult(BaseModel):
    answer: str
    steps: list[TraceStep]
    usage: Usage
    stopped: str = Field(description="'answer', 'max_steps' or 'error'")


class Agent:
    def __init__(
        self,
        llm: LLM,
        ctx: ToolContext,
        registry: ToolRegistry | None = None,
        *,
        max_steps: int = 8,
    ) -> None:
        self.llm, self.ctx = llm, ctx
        self.registry = registry or ToolRegistry()
        self.max_steps = max_steps

    async def run(self, question: str, *, document_id: str | None = None) -> AgentResult:
        system = AGENT_SYSTEM.format(tools=self.registry.describe())
        opening = question if document_id is None else f"Document id: {document_id}\n\n{question}"
        messages = [Message("user", opening)]
        steps: list[TraceStep] = []
        usage = Usage()

        for _ in range(self.max_steps):
            try:
                completion = await self.llm.complete(
                    system=system, messages=messages, schema=AgentAction
                )
            except LLMError as exc:
                return AgentResult(
                    answer=f"Agent error: {exc}", steps=steps, usage=usage, stopped="error"
                )
            usage.add(completion.usage)
            action = completion.parsed
            assert action is not None
            messages.append(Message("assistant", action.model_dump_json()))

            if action.action == "final_answer":
                steps.append(TraceStep(action="final_answer", arguments={}, thought=action.thought))
                return AgentResult(
                    answer=action.answer or "", steps=steps, usage=usage, stopped="answer"
                )

            started = time.perf_counter()
            step = TraceStep(
                action=action.action, arguments=action.arguments, thought=action.thought
            )
            try:
                result = await self.registry.call(self.ctx, action.action, action.arguments)
                text = json.dumps(result, ensure_ascii=False, default=str)
                if len(text) > MAX_OBSERVATION_CHARS:
                    text = text[:MAX_OBSERVATION_CHARS] + " ...[truncated]"
                step.observation = text
                feedback = f"Observation:\n{text}"
            except ToolError as exc:
                step.error = str(exc)
                feedback = f"Tool error: {exc}"
            step.seconds = time.perf_counter() - started
            steps.append(step)
            messages.append(Message("user", feedback))

        return AgentResult(
            answer="I could not finish within the step limit. Partial findings are in the trace.",
            steps=steps,
            usage=usage,
            stopped="max_steps",
        )
