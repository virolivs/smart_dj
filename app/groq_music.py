from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .groq_vision import GROQ_API_URL


DEFAULT_MUSIC_MODEL = "groq/compound-mini"


@dataclass(frozen=True)
class MusicProfile:
    id: str
    energy: float
    danceability: float
    bpm: int | None
    genre: str
    confidence: float
    reason: str


class GroqMusicResearcher:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        opener: Callable[..., object] = urlopen,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MUSIC_MODEL", DEFAULT_MUSIC_MODEL)
        self.opener = opener

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def research(self, tracks: list[dict[str, str]]) -> list[MusicProfile]:
        if not self.enabled:
            raise RuntimeError("GROQ_API_KEY is not configured")

        requested_ids = {track["id"] for track in tracks}
        prompt = (
            "Research the following songs on the web. Prefer reliable music databases, "
            "artist pages and multiple corroborating results. Identify the exact recording, "
            "not another song with a similar title. Estimate when exact data is unavailable. "
            "For each input id return: id, energy (0..1), danceability (0..1), bpm "
            "(integer 40..240 or null), genre (short), confidence (0..1), and reason in "
            "Brazilian Portuguese (max 120 characters). Energy means perceived musical "
            "intensity, not popularity. Return only one JSON object shaped as "
            '{"tracks":[...]} and preserve every id exactly.\n\nSongs:\n'
            + json.dumps(tracks, ensure_ascii=False)
        )
        body = {
            "model": self.model,
            "temperature": 0.1,
            "max_completion_tokens": 900,
            "messages": [{"role": "user", "content": prompt}],
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
        try:
            with self.opener(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(detail)["error"]["message"]
            except (KeyError, TypeError, json.JSONDecodeError):
                message = f"HTTP {exc.code}"
            raise RuntimeError(f"Groq music research failed: {message}") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
            parsed = self._parse_json_object(content)
            raw_profiles = parsed["tracks"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Groq returned an invalid music research response") from exc

        profiles: list[MusicProfile] = []
        seen: set[str] = set()
        for item in raw_profiles:
            track_id = str(item.get("id", ""))
            if track_id not in requested_ids or track_id in seen:
                continue
            seen.add(track_id)
            profiles.append(
                MusicProfile(
                    id=track_id,
                    energy=self._bounded_float(item.get("energy", 0.5)),
                    danceability=self._bounded_float(item.get("danceability", 0.5)),
                    bpm=self._nullable_bpm(item.get("bpm")),
                    genre=str(item.get("genre") or "desconhecido")[:80],
                    confidence=self._bounded_float(item.get("confidence", 0.4)),
                    reason=str(item.get("reason") or "Estimativa da pesquisa web.")[:160],
                )
            )
        if not profiles:
            raise RuntimeError("Groq did not return any matching music profiles")
        return profiles

    @staticmethod
    def _parse_json_object(content: str) -> dict:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise
            return json.loads(cleaned[start : end + 1])

    @staticmethod
    def _bounded_float(value: object) -> float:
        return round(max(0.0, min(1.0, float(value))), 3)

    @staticmethod
    def _nullable_bpm(value: object) -> int | None:
        if value is None:
            return None
        bpm = int(round(float(value)))
        return max(40, min(240, bpm))
