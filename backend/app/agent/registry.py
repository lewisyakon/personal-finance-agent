"""Fixed Agent registry and namespace enforcement."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    responsibility: str
    writable_namespaces: frozenset[str]


class AgentRegistry:
    def __init__(self, definitions: tuple[AgentDefinition, ...]) -> None:
        self._definitions = {item.name: item for item in definitions}
        if len(self._definitions) != len(definitions):
            raise ValueError("Agent Registry 名称重复")

    def get(self, name: str) -> AgentDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise ValueError(f"未知 Agent: {name}") from exc

    def validate_update(self, name: str, update: dict) -> None:
        definition = self.get(name)
        runtime_fields = {
            "status",
            "answer",
            "error_code",
            "error_message",
            "errors",
            "step_count",
            "tool_call_count",
            "model_call_count",
            "token_usage",
        }
        unexpected = set(update) - definition.writable_namespaces - runtime_fields
        if unexpected:
            raise ValueError(f"Agent {name} 越权更新共享状态: {sorted(unexpected)}")

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))


fixed_agent_registry = AgentRegistry(
    (
        AgentDefinition(
            "supervisor",
            "理解意图、约束并生成固定 Analysis 计划",
            frozenset({"normalized_intent", "constraints", "plan", "supervisor_handoff"}),
        ),
        AgentDefinition(
            "analysis",
            "通过只读 Tool 获取事实并生成带 Evidence 的分析",
            frozenset(
                {
                    "task_results",
                    "statistics",
                    "findings",
                    "evidence_refs",
                    "analysis_handoff",
                    "tool_names",
                    "tool_results",
                }
            ),
        ),
        AgentDefinition(
            "verifier",
            "验证金额、时间范围、方向、计划 Tool 和 Evidence",
            frozenset({"verification"}),
        ),
    )
)
