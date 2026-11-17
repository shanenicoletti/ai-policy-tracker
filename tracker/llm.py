"""
llm.py - Talks to Gemini, with backup models.

If the main model is overloaded (Google's servers say "high demand") or
retired, we wait a little and retry, then switch to a backup model instead
of crashing. Once we switch, we stay on that backup for the rest of the run.
"""

import os
import time

from google import genai

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_BACKUPS = "gemini-3.7-flash,gemini-3.5-flash-lite"

RETRYABLE = {429, 500, 503, 504}   # busy or rate-limited: worth waiting
SKIP_MODEL = {404}                 # model not available: go straight to the next one


class GeminiUnavailable(Exception):
    """Every model we tried is down."""


class Gemini:
    def __init__(self):
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        main = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        backups = os.environ.get("GEMINI_BACKUP_MODELS") or DEFAULT_BACKUPS
        self.models = [main] + [m.strip() for m in backups.split(",") if m.strip() and m.strip() != main]
        self.current = 0

    @property
    def model(self) -> str:
        return self.models[self.current]

    def generate(self, contents, config):
        while self.current < len(self.models):
            for attempt in range(3):
                try:
                    return self.client.models.generate_content(
                        model=self.model, contents=contents, config=config)
                except genai.errors.APIError as e:
                    code = getattr(e, "code", None)
                    if code in SKIP_MODEL:
                        print(f"  {self.model} is not available ({code}).")
                        break
                    if code in RETRYABLE and attempt < 2:
                        wait = 30 * (attempt + 1)
                        print(f"  {self.model} busy ({code}), waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    if code in RETRYABLE:
                        print(f"  {self.model} still busy ({code}).")
                        break
                    raise  # a real error (bad request, bad key): don't hide it
            self.current += 1
            if self.current < len(self.models):
                print(f"  Switching to backup model {self.model}.")
        raise GeminiUnavailable("All Gemini models are busy or unavailable right now.")
