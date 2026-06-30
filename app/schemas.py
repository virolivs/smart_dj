from pydantic import BaseModel, Field
from typing import Optional


class SessionResponse(BaseModel):
    session_id: str


class TrackResponse(BaseModel):
    title: str
    artist: str
    level: str
    bpm: int
    audio_url: str
    source_url: str
    license: str
    attribution: str


class AnalyzeRequest(BaseModel):
    session_id: str
    width: int = Field(ge=1, le=320)
    height: int = Field(ge=1, le=240)
    pixels: list[int]


class SimulateRequest(BaseModel):
    session_id: str
    level: str


class AnalysisResponse(BaseModel):
    motion_score: float
    energy_level: str
    current_track: TrackResponse
    changed_track: bool
    seconds_until_next_change: float


class AppConfigResponse(BaseModel):
    spotify_client_id: Optional[str]
    groq_enabled: bool
    ai_provider: str = "gemini"
    ai_model: str
    ai_key_fingerprint: Optional[str] = None
    vision_interval_seconds: int
    min_track_seconds: int


class VisionAnalyzeRequest(BaseModel):
    frames: list[str] = Field(min_length=1, max_length=5)
    motion_scores: list[float] = Field(default_factory=list, max_length=120)


class VisionAnalyzeResponse(BaseModel):
    energy: float = Field(ge=0, le=1)
    level: str
    confidence: float = Field(ge=0, le=1)
    people_count: Optional[int] = Field(default=None, ge=0)
    active_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    summary: str
    provider: str = "groq"


class MusicResearchTrack(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(min_length=1, max_length=300)


class MusicResearchRequest(BaseModel):
    tracks: list[MusicResearchTrack] = Field(min_length=1, max_length=2)


class MusicProfileResponse(BaseModel):
    id: str
    energy: float = Field(ge=0, le=1)
    danceability: float = Field(ge=0, le=1)
    bpm: Optional[int] = Field(default=None, ge=40, le=240)
    genre: str
    confidence: float = Field(ge=0, le=1)
    reason: str


class MusicResearchResponse(BaseModel):
    tracks: list[MusicProfileResponse]
    provider: str = "gemini-3.1-flash-lite"


class JourneyCatalogTrack(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    artists: str = Field(min_length=1, max_length=500)
    uri: str = Field(min_length=1, max_length=200)
    energy: float = Field(default=0.5, ge=0, le=1)
    danceability: float = Field(default=0.5, ge=0, le=1)
    bpm: Optional[int] = Field(default=None, ge=40, le=240)
    genre: str = Field(default="desconhecido", max_length=80)
    confidence: float = Field(default=0.35, ge=0, le=1)
    reason: str = Field(default="Perfil estimado.", max_length=180)


class JourneyGenerateRequest(BaseModel):
    situation: str = Field(default="", max_length=800)
    venue: str = Field(default="resenha", max_length=40)
    start_energy: str = Field(default="calmo", max_length=40)
    end_energy: str = Field(default="mais_intenso", max_length=40)
    discovery: str = Field(default="equilibrado", max_length=40)
    total_tracks: int = Field(default=20, ge=8, le=40)
    tracks: list[JourneyCatalogTrack] = Field(min_length=1, max_length=250)


class JourneyTrackResponse(BaseModel):
    id: str
    name: str
    artists: str
    uri: str
    energy: float
    danceability: float
    bpm: Optional[int] = None
    genre: str
    confidence: float
    reason: str
    phase_reason: str


class JourneyPhaseResponse(BaseModel):
    name: str
    intent: str
    energy_target: float
    tracks: list[JourneyTrackResponse]


class JourneyResponse(BaseModel):
    title: str
    summary: str
    explanation: str
    phases: list[JourneyPhaseResponse]


class JourneyPlanRequest(BaseModel):
    situation: str = Field(default="", max_length=800)
    venue: str = Field(default="resenha", max_length=40)
    start_energy: str = Field(default="calmo", max_length=40)
    end_energy: str = Field(default="mais_intenso", max_length=40)
    discovery: str = Field(default="equilibrado", max_length=40)
    total_tracks: int = Field(default=20, ge=8, le=40)
    feedback: str = Field(default="", max_length=600)


class PlannedTrackResponse(BaseModel):
    title: str
    artist: str
    energy: float = Field(ge=0, le=1)
    danceability: float = Field(ge=0, le=1)
    bpm:  Optional[int] = Field(default=None, ge=40, le=240)
    genre: str
    reason: str
    search_query: str


class PlannedPhaseResponse(BaseModel):
    name: str
    intent: str
    energy_target: float = Field(ge=0, le=1)
    tracks: list[PlannedTrackResponse]


class JourneyPlanResponse(BaseModel):
    title: str
    summary: str
    explanation: str
    phases: list[PlannedPhaseResponse]
    provider: str = "gemini-3.1-flash-lite"
