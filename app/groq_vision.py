from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Callable
from urllib.request import Request, urlopen


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_FRAME_BYTES = 750_000


@dataclass(frozen=True)
class VisionResult:
    energy: float
    level: str
    confidence: float
    people_count: int | None
    active_ratio: float | None
    summary: str


def energy_level(energy: float) -> str:
    if energy < 0.34:
        return "calma"
    if energy < 0.67:
        return "media"
    return "alta"


class GroqVisionAnalyzer:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        opener: Callable[..., object] = urlopen,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_VISION_MODEL", DEFAULT_MODEL)
        self.opener = opener

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def analyze(self, frames: list[str], motion_scores: list[float]) -> VisionResult:
        if not self.enabled:
            raise RuntimeError("GROQ_API_KEY is not configured")

        image_parts = [
            {"type": "image_url", "image_url": {"url": self._validated_data_url(frame)}}
            for frame in frames
        ]
        motion_context = self._motion_context(motion_scores)
        prompt = (
            "You analyze a dance floor using a few chronological camera samples from one minute. "
            "Estimate collective activity, not emotions and not whether people liked the music. "
            "Do not identify people. Ignore lighting changes, screens and camera noise when possible. "
            f"Local frame-difference context: {motion_context}. "
            "Return JSON only with: energy (0..1), confidence (0..1), people_count "
            "(integer or null), active_ratio (0..1 or null), and summary in Brazilian Portuguese "
            "(max 140 characters). Energy means sustained collective bodily activity."
        )
        body = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}, *image_parts],
                }
            ],
        }
        request = Request(
            GROQ_API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "dj-copilot/1.0",
            },
            method="POST",
        )
        with self.opener(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))

        try:
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Groq returned an invalid vision response") from exc

        energy = self._bounded_float(parsed.get("energy"))
        confidence = self._bounded_float(parsed.get("confidence"))
        people_count = self._nullable_int(parsed.get("people_count"))
        active_ratio = self._nullable_bounded_float(parsed.get("active_ratio"))
        summary = str(parsed.get("summary") or "Análise visual concluída.")[:180]
        return VisionResult(
            energy=energy,
            level=energy_level(energy),
            confidence=confidence,
            people_count=people_count,
            active_ratio=active_ratio,
            summary=summary,
        )

    @staticmethod
    def _validated_data_url(frame: str) -> str:
        prefixes = ("data:image/jpeg;base64,", "data:image/png;base64,")
        prefix = next((item for item in prefixes if frame.startswith(item)), None)
        if prefix is None:
            raise ValueError("Frames must be JPEG or PNG data URLs")
        try:
            decoded = base64.b64decode(frame[len(prefix) :], validate=True)
        except ValueError as exc:
            raise ValueError("Frame contains invalid base64 data") from exc
        if not decoded or len(decoded) > MAX_FRAME_BYTES:
            raise ValueError("Frame is empty or too large")
        return frame

    @staticmethod
    def _motion_context(scores: list[float]) -> str:
        if not scores:
            return "unavailable"
        recent = scores[-60:]
        average = sum(recent) / len(recent)
        return f"mean={average:.2f}, min={min(recent):.2f}, max={max(recent):.2f}"

    @staticmethod
    def _bounded_float(value: object) -> float:
        number = float(value)
        return round(max(0.0, min(1.0, number)), 3)

    @classmethod
    def _nullable_bounded_float(cls, value: object) -> float | None:
        if value is None:
            return None
        return cls._bounded_float(value)

    @staticmethod
    def _nullable_int(value: object) -> int | None:
        if value is None:
            return None
        return max(0, int(value))
