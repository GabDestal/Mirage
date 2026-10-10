def run(agent, task: str) -> str:
    """Run one task, print each tool call and result, return the final answer."""
    final = ""
    for update in agent.stream({"messages": [("user", task)]}, stream_mode="updates"):
        for step in update.values():
            for msg in (step or {}).get("messages", []):
                for tc in getattr(msg, "tool_calls", None) or []:
                    print(f"  → {tc['name']}({tc['args']})")
                if msg.type == "tool":
                    print(f"  ← {str(msg.content)[:160]}")
                elif msg.type == "ai" and msg.content:
                    final = msg.content if isinstance(msg.content, str) else str(msg.content)
    print(final)
    return final
