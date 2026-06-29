from pydantic import BaseModel, Field


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
    spotify_client_id: str | None
    groq_enabled: bool
    vision_interval_seconds: int
    min_track_seconds: int


class VisionAnalyzeRequest(BaseModel):
    frames: list[str] = Field(min_length=1, max_length=5)
    motion_scores: list[float] = Field(default_factory=list, max_length=120)


class VisionAnalyzeResponse(BaseModel):
    energy: float = Field(ge=0, le=1)
    level: str
    confidence: float = Field(ge=0, le=1)
    people_count: int | None = Field(default=None, ge=0)
    active_ratio: float | None = Field(default=None, ge=0, le=1)
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
    bpm: int | None = Field(default=None, ge=40, le=240)
    genre: str
    confidence: float = Field(ge=0, le=1)
    reason: str


class MusicResearchResponse(BaseModel):
    tracks: list[MusicProfileResponse]
    provider: str = "groq-compound"
