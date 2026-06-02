"""Agent meta tools for adapter dispatch."""

from ...contracts import envelope
from ...doctor import AgentDoctor


def doctor(skip_network: bool = False, check_mcp: bool = True) -> dict:
    return envelope(
        AgentDoctor().run(skip_network=skip_network, check_mcp=check_mcp),
        meta={"tool": "agent.doctor"},
    )
