import json
import os
import re
import httpx


class MockProvider:
    """Keyword-based fixture adapter; does not receive expected test labels.

    This is a deterministic integration aid, not an LLM quality measurement.
    Omitting the word JSON from the prompt deliberately yields plain text.
    Omitting the word urgent disables priority handling.
    """
    def complete(self, prompt, ticket):
        text = ticket.lower()
        instructions = prompt.replace(ticket, "").lower()
        groups = {
            "bug": ("crash", "error", "broken", "freeze", "defect"),
            "billing": ("invoice", "refund", "charge", "payment", "subscription"),
            "feature": ("feature", "export", "integration", "dark mode", "shortcut"),
            "account": ("password", "login", "sign in", "profile", "verification"),
        }
        category = next((name for name, words in groups.items()
                         if any(word in text for word in words)), "account")
        priority = "high" if "urgent" in instructions and re.search(r"\burgent\b", text) else "normal"
        if "json" not in instructions:
            return f"{category}: {priority}"
        return json.dumps({"category": category, "priority": priority})

    def close(self):
        pass


class HTTPProvider:
    def __init__(self, model):
        self.model = model
        self.url = os.environ.get("PROMPTLAB_PROVIDER_URL", "")
        if not self.url.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
            raise ValueError("Set a full HTTPS or loopback chat completions URL")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(timeout=15, headers=headers, follow_redirects=False)

    def complete(self, prompt, ticket):
        with self.client.stream("POST", self.url, json={
            "model": self.model, "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 1_048_576:
                    raise ValueError("Provider response exceeds 1 MiB")
        text = json.loads(body)["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError("Provider did not return text")
        return text

    def close(self):
        self.client.close()


def make_provider(kind, model):
    if kind == "mock":
        return MockProvider()
    if kind == "http":
        return HTTPProvider(model)
    raise ValueError("Unknown provider")
