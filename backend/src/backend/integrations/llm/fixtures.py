from __future__ import annotations

from backend.schemas import ResolvedProviderConfig


class FixtureChatModelAdapter:
    def generate_text(self, provider: ResolvedProviderConfig, messages: list[dict]) -> str:
        user_content = "\n".join(str(message.get("content", "")) for message in messages if message.get("role") == "user")
        title = provider.settings.get("title", "Fixture Report")
        return f"# {title}\n\n{user_content[:1000]}\n\n## Evidence\n\nThis fixture report cites the supplied evidence chunks."
