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


@dataclass(frozen=True)
class JourneyTrack:
    id: str
    name: str
    artists: str
    uri: str
    energy: float
    danceability: float
    bpm: int | None
    genre: str
    confidence: float
    reason: str
    phase_reason: str


@dataclass(frozen=True)
class JourneyPhase:
    name: str
    intent: str
    energy_target: float
    tracks: tuple[JourneyTrack, ...]


@dataclass(frozen=True)
class JourneyResult:
    title: str
    summary: str
    explanation: str
    phases: tuple[JourneyPhase, ...]


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


class JourneyGenerator:
    ENERGY_VALUES = {
        "calmo": 0.24,
        "medio": 0.5,
        "animado": 0.74,
        "mais_calmo": 0.28,
        "mais_intenso": 0.78,
        "no_pico": 0.88,
    }

    VENUE_LABELS = {
        "sozinho": "Escuta pessoal",
        "festa": "Festa",
        "treino": "Treino",
        "estudo": "Foco",
        "viagem": "Viagem",
        "date": "Date",
        "resenha": "Resenha",
    }

    def generate(
        self,
        *,
        situation: str,
        venue: str,
        start_energy: str,
        end_energy: str,
        discovery: str,
        total_tracks: int,
        tracks: list[dict],
    ) -> JourneyResult:
        if not tracks:
            raise ValueError("Catalog cannot be empty")
        if total_tracks < 8 or total_tracks > 40:
            raise ValueError("Total tracks must be between 8 and 40")

        targets = self._phase_targets(start_energy, end_energy)
        counts = self._phase_counts(total_tracks)
        phase_specs = (
            ("Chegada", "Abrir com músicas acessíveis para colocar todo mundo na mesma vibe."),
            ("Aquecimento", "Aumentar ritmo e dançabilidade sem queimar o pico cedo demais."),
            ("Pico", "Concentrar as faixas mais fortes, dançantes e memoráveis do roteiro."),
            ("Fechamento", "Encerrar com energia controlada para a playlist não terminar seca."),
        )

        selected_ids: set[str] = set()
        phases: list[JourneyPhase] = []
        previous_bpm: int | None = None
        for index, ((name, intent), target, count) in enumerate(zip(phase_specs, targets, counts)):
            chosen = self._choose_tracks(
                tracks=tracks,
                target=target,
                count=count,
                discovery=discovery,
                selected_ids=selected_ids,
                previous_bpm=previous_bpm,
                phase_index=index,
            )
            journey_tracks = []
            for track in chosen:
                selected_ids.add(str(track["id"]))
                previous_bpm = track.get("bpm") or previous_bpm
                journey_tracks.append(
                    JourneyTrack(
                        id=str(track["id"]),
                        name=str(track["name"]),
                        artists=str(track["artists"]),
                        uri=str(track["uri"]),
                        energy=self._bounded_float(track.get("energy", 0.5)),
                        danceability=self._bounded_float(track.get("danceability", 0.5)),
                        bpm=track.get("bpm"),
                        genre=str(track.get("genre") or "desconhecido"),
                        confidence=self._bounded_float(track.get("confidence", 0.35)),
                        reason=str(track.get("reason") or "Perfil estimado."),
                        phase_reason=self._phase_reason(track, target, name),
                    )
                )
            phases.append(
                JourneyPhase(
                    name=name,
                    intent=intent,
                    energy_target=round(target, 2),
                    tracks=tuple(journey_tracks),
                )
            )

        venue_label = self.VENUE_LABELS.get(venue, venue).strip().title()
        title = self._title(venue_label, start_energy, end_energy)
        summary = self._summary(situation, venue_label)
        explanation = self._explanation(start_energy, end_energy, discovery)
        return JourneyResult(title=title, summary=summary, explanation=explanation, phases=tuple(phases))

    def _choose_tracks(
        self,
        *,
        tracks: list[dict],
        target: float,
        count: int,
        discovery: str,
        selected_ids: set[str],
        previous_bpm: int | None,
        phase_index: int,
    ) -> list[dict]:
        available = [track for track in tracks if str(track.get("id")) not in selected_ids]
        if len(available) < count:
            available = tracks
        ranked = sorted(
            available,
            key=lambda track: self._score_track(track, target, discovery, previous_bpm, phase_index),
        )
        return ranked[:count]

    def _score_track(
        self,
        track: dict,
        target: float,
        discovery: str,
        previous_bpm: int | None,
        phase_index: int,
    ) -> float:
        energy = self._bounded_float(track.get("energy", 0.5))
        danceability = self._bounded_float(track.get("danceability", 0.5))
        confidence = self._bounded_float(track.get("confidence", 0.35))
        bpm = track.get("bpm")
        energy_distance = abs(energy - target)
        dance_target = min(0.95, 0.42 + target * 0.55)
        dance_distance = abs(danceability - dance_target)
        confidence_penalty = 1 - confidence
        bpm_penalty = 0.12
        if previous_bpm and bpm:
            bpm_penalty = min(1.0, abs(int(bpm) - previous_bpm) / 42)
        discovery_penalty = 0.0
        if discovery == "mais_conhecidas":
            discovery_penalty = confidence_penalty * 0.22
        elif discovery == "mais_descobertas":
            discovery_penalty = confidence * 0.12
        peak_bonus = -danceability * 0.08 if phase_index == 2 else 0.0
        return (
            energy_distance * 0.56
            + dance_distance * 0.2
            + bpm_penalty * 0.12
            + confidence_penalty * 0.08
            + discovery_penalty
            + peak_bonus
        )

    def _phase_targets(self, start_energy: str, end_energy: str) -> tuple[float, float, float, float]:
        start = self.ENERGY_VALUES.get(start_energy, 0.5)
        end = self.ENERGY_VALUES.get(end_energy, 0.78)
        peak = max(start, end, 0.82 if end_energy == "no_pico" else 0.76)
        warmup = min(0.86, (start + peak) / 2)
        close = end if end_energy != "no_pico" else peak
        return (start, warmup, peak, close)

    @staticmethod
    def _phase_counts(total_tracks: int) -> tuple[int, int, int, int]:
        weights = (0.2, 0.3, 0.34, 0.16)
        counts = [max(1, int(total_tracks * weight)) for weight in weights]
        while sum(counts) < total_tracks:
            counts[2] += 1
        while sum(counts) > total_tracks:
            largest = max(range(len(counts)), key=lambda index: counts[index])
            counts[largest] -= 1
        return tuple(counts)  # type: ignore[return-value]

    @staticmethod
    def _phase_reason(track: dict, target: float, phase_name: str) -> str:
        energy = round(float(track.get("energy", 0.5)) * 100)
        bpm = track.get("bpm")
        bpm_text = f" e {bpm} BPM" if bpm else ""
        return f"Entra em {phase_name.lower()} por ficar perto do alvo de energia ({energy}%){bpm_text}."

    @staticmethod
    def _title(venue_label: str, start_energy: str, end_energy: str) -> str:
        if start_energy == "calmo" and end_energy in {"mais_intenso", "no_pico"}:
            return f"{venue_label} que cresce ate o pico"
        if end_energy == "mais_calmo":
            return f"{venue_label} com pouso suave"
        return f"{venue_label} em progressao"

    @staticmethod
    def _summary(situation: str, venue_label: str) -> str:
        cleaned = " ".join(situation.strip().split())
        if not cleaned:
            return f"Roteiro musical para {venue_label.lower()}."
        return cleaned[:220]

    @staticmethod
    def _explanation(start_energy: str, end_energy: str, discovery: str) -> str:
        discovery_text = {
            "mais_conhecidas": "priorizando faixas mais seguras e reconheciveis",
            "mais_descobertas": "abrindo espaco para descobertas",
            "equilibrado": "equilibrando seguranca e descoberta",
        }.get(discovery, "equilibrando seguranca e descoberta")
        return (
            "A sequencia foi montada em quatro blocos para criar narrativa: "
            f"comeca em {start_energy}, sobe gradualmente ate o pico e termina em {end_energy}, "
            f"{discovery_text}. O score considera energia, dancabilidade, BPM, confianca do perfil "
            "e evita repetir a mesma faixa em blocos diferentes."
        )

    @staticmethod
    def _bounded_float(value: object) -> float:
        return round(max(0.0, min(1.0, float(value))), 3)
