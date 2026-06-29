from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Callable
from uuid import uuid4


ENERGY_LEVELS = ("calma", "media", "alta")


@dataclass(frozen=True)
class Track:
    title: str
    artist: str
    level: str
    bpm: int
    audio_url: str
    source_url: str
    license: str
    attribution: str


TRACKS: tuple[Track, ...] = (
    Track(
        "Deep Relaxation",
        "Kevin MacLeod",
        "calma",
        85,
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Deep%20Relaxation.mp3",
        "https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1100398",
        "Creative Commons BY 4.0",
        "Deep Relaxation by Kevin MacLeod (incompetech.com)",
    ),
    Track(
        "Carefree",
        "Kevin MacLeod",
        "calma",
        90,
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Carefree.mp3",
        "https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1400037",
        "Creative Commons BY 4.0",
        "Carefree by Kevin MacLeod (incompetech.com)",
    ),
    Track(
        "Airport Lounge",
        "Kevin MacLeod",
        "media",
        116,
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Airport%20Lounge.mp3",
        "https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1100806",
        "Creative Commons BY 4.0",
        "Airport Lounge by Kevin MacLeod (incompetech.com)",
    ),
    Track(
        "Disco Medusae",
        "Kevin MacLeod",
        "media",
        120,
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Disco%20Medusae.mp3",
        "https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1200088",
        "Creative Commons BY 4.0",
        "Disco Medusae by Kevin MacLeod (incompetech.com)",
    ),
    Track(
        "EDM Detection Mode",
        "Kevin MacLeod",
        "alta",
        128,
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/EDM%20Detection%20Mode.mp3",
        "https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1500026",
        "Creative Commons BY 4.0",
        "EDM Detection Mode by Kevin MacLeod (incompetech.com)",
    ),
    Track(
        "Electrodoodle",
        "Kevin MacLeod",
        "alta",
        142,
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Electrodoodle.mp3",
        "https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1200079",
        "Creative Commons BY 4.0",
        "Electrodoodle by Kevin MacLeod (incompetech.com)",
    ),
)


@dataclass
class AnalysisResult:
    motion_score: float
    energy_level: str
    current_track: Track
    changed_track: bool
    seconds_until_next_change: float


@dataclass
class SessionState:
    session_id: str
    last_frame: list[int] | None = None
    current_level: str = "calma"
    track_index_by_level: dict[str, int] = field(default_factory=dict)
    current_track: Track = field(default_factory=lambda: tracks_for_level("calma")[0])
    last_change_at: float = 0.0
    noise_floor: float = 4.0
    smoothed_motion_score: float = 0.0


def tracks_for_level(level: str) -> list[Track]:
    return [track for track in TRACKS if track.level == level]


class MotionAnalyzer:
    def __init__(self, calm_threshold: float = 6.0, high_threshold: float = 18.0) -> None:
        self.calm_threshold = calm_threshold
        self.high_threshold = high_threshold

    def score(self, previous: list[int] | None, current: list[int]) -> float:
        if previous is None or not current:
            return 0.0
        if len(previous) != len(current):
            raise ValueError("Frames must have the same number of pixels")
        total = sum(abs(a - b) for a, b in zip(previous, current))
        return total / len(current)

    def classify(self, motion_score: float) -> str:
        if motion_score < self.calm_threshold:
            return "calma"
        if motion_score < self.high_threshold:
            return "media"
        return "alta"

    def calibrated_score(self, state: SessionState, raw_score: float) -> float:
        if raw_score < self.high_threshold:
            state.noise_floor = (state.noise_floor * 0.9) + (raw_score * 0.1)
        adjusted_score = max(0.0, raw_score - (state.noise_floor * 1.8))
        state.smoothed_motion_score = (state.smoothed_motion_score * 0.65) + (adjusted_score * 0.35)
        return state.smoothed_motion_score


class DJEngine:
    def __init__(
        self,
        analyzer: MotionAnalyzer | None = None,
        min_seconds_between_changes: float = 8.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.analyzer = analyzer or MotionAnalyzer()
        self.min_seconds_between_changes = min_seconds_between_changes
        self.clock = clock
        self.sessions: dict[str, SessionState] = {}

    def create_session(self) -> SessionState:
        session_id = uuid4().hex
        state = SessionState(session_id=session_id, last_change_at=self.clock())
        self.sessions[session_id] = state
        return state

    def get_session(self, session_id: str) -> SessionState:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise KeyError("Session not found") from exc

    def analyze(self, session_id: str, pixels: list[int]) -> AnalysisResult:
        state = self.get_session(session_id)
        self._validate_pixels(pixels)

        raw_motion_score = self.analyzer.score(state.last_frame, pixels)
        motion_score = self.analyzer.calibrated_score(state, raw_motion_score)
        detected_level = self.analyzer.classify(motion_score)
        now = self.clock()
        elapsed = now - state.last_change_at
        can_change = elapsed >= self.min_seconds_between_changes
        changed_track = False

        if detected_level != state.current_level and can_change:
            state.current_level = detected_level
            state.current_track = self._next_track_for_level(state, detected_level)
            state.last_change_at = now
            changed_track = True

        state.last_frame = pixels
        seconds_left = max(0.0, self.min_seconds_between_changes - (now - state.last_change_at))

        return AnalysisResult(
            motion_score=round(motion_score, 2),
            energy_level=state.current_level,
            current_track=state.current_track,
            changed_track=changed_track,
            seconds_until_next_change=round(seconds_left, 2),
        )

    def simulate(self, session_id: str, level: str) -> AnalysisResult:
        if level not in ENERGY_LEVELS:
            raise ValueError("Invalid energy level")
        state = self.get_session(session_id)
        now = self.clock()
        changed_track = False

        if level != state.current_level:
            state.current_level = level
            state.current_track = self._next_track_for_level(state, level)
            state.last_change_at = now
            changed_track = True

        return AnalysisResult(
            motion_score={"calma": 3.0, "media": 14.0, "alta": 32.0}[level],
            energy_level=state.current_level,
            current_track=state.current_track,
            changed_track=changed_track,
            seconds_until_next_change=self.min_seconds_between_changes,
        )

    def _next_track_for_level(self, state: SessionState, level: str) -> Track:
        tracks = tracks_for_level(level)
        current_index = state.track_index_by_level.get(level, -1)
        next_index = (current_index + 1) % len(tracks)
        state.track_index_by_level[level] = next_index
        return tracks[next_index]

    @staticmethod
    def _validate_pixels(pixels: list[int]) -> None:
        if not pixels:
            raise ValueError("Frame cannot be empty")
        if any(pixel < 0 or pixel > 255 for pixel in pixels):
            raise ValueError("Pixels must be between 0 and 255")
