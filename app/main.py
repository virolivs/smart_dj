from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .domain import DJEngine, ENERGY_LEVELS, TRACKS, AnalysisResult
from .groq_music import GroqMusicResearcher
from .groq_vision import GroqVisionAnalyzer
from .schemas import (
    AnalysisResponse,
    AnalyzeRequest,
    AppConfigResponse,
    MusicResearchRequest,
    MusicResearchResponse,
    SessionResponse,
    SimulateRequest,
    TrackResponse,
    VisionAnalyzeRequest,
    VisionAnalyzeResponse,
)


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(
    title="DJ Interativo",
    description="Sistema interativo de playlist baseada em movimento do publico.",
    version="1.0.0",
)
VISION_INTERVAL_SECONDS = int(os.getenv("VISION_INTERVAL_SECONDS", "60"))
MIN_TRACK_SECONDS = int(os.getenv("MIN_TRACK_SECONDS", "120"))
engine = DJEngine(min_seconds_between_changes=MIN_TRACK_SECONDS)
vision_analyzer = GroqVisionAnalyzer()
music_researcher = GroqMusicResearcher()
static_dir = Path(__file__).parent / "static"


def to_response(result: AnalysisResult) -> AnalysisResponse:
    return AnalysisResponse(
        motion_score=result.motion_score,
        energy_level=result.energy_level,
        current_track=TrackResponse(**result.current_track.__dict__),
        changed_track=result.changed_track,
        seconds_until_next_change=result.seconds_until_next_change,
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", response_model=AppConfigResponse)
def config() -> AppConfigResponse:
    return AppConfigResponse(
        spotify_client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        groq_enabled=vision_analyzer.enabled,
        vision_interval_seconds=VISION_INTERVAL_SECONDS,
        min_track_seconds=MIN_TRACK_SECONDS,
    )


@app.post("/api/sessions", response_model=SessionResponse)
def create_session() -> SessionResponse:
    state = engine.create_session()
    return SessionResponse(session_id=state.session_id)


@app.get("/api/playlists", response_model=list[TrackResponse])
def playlists() -> list[TrackResponse]:
    return [TrackResponse(**track.__dict__) for track in TRACKS]


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze(payload: AnalyzeRequest) -> AnalysisResponse:
    if payload.width * payload.height != len(payload.pixels):
        raise HTTPException(status_code=422, detail="Frame dimensions do not match pixel count")
    try:
        return to_response(engine.analyze(payload.session_id, payload.pixels))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/simulate", response_model=AnalysisResponse)
def simulate(payload: SimulateRequest) -> AnalysisResponse:
    if payload.level not in ENERGY_LEVELS:
        raise HTTPException(status_code=422, detail="Invalid energy level")
    try:
        return to_response(engine.simulate(payload.session_id, payload.level))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/vision/analyze", response_model=VisionAnalyzeResponse)
def analyze_vision(payload: VisionAnalyzeRequest) -> VisionAnalyzeResponse:
    try:
        result = vision_analyzer.analyze(payload.frames, payload.motion_scores)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        status = 503 if not vision_analyzer.enabled else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Groq vision request failed") from exc
    return VisionAnalyzeResponse(**result.__dict__)


@app.post("/api/music/research", response_model=MusicResearchResponse)
def research_music(payload: MusicResearchRequest) -> MusicResearchResponse:
    try:
        profiles = music_researcher.research(
            [track.model_dump() for track in payload.tracks]
        )
    except RuntimeError as exc:
        status = 503 if not music_researcher.enabled else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Groq music research failed") from exc
    return MusicResearchResponse(tracks=[profile.__dict__ for profile in profiles])


app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")
