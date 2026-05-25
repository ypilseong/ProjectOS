import os

# Provide a dummy API key so LLMClient can be instantiated during tests
# without hitting real credentials validation at module import time.
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
