from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MUSIC_MODEL = "gemini-3.1-flash-lite"


@dataclass(frozen=True)
class MusicProfile:
    id: str
    energy: float
    danceability: float
    bpm: int | None
    genre: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class PlannedTrack:
    title: str
    artist: str
    energy: float
    danceability: float
    bpm: int | None
    genre: str
    reason: str
    search_query: str


@dataclass(frozen=True)
class PlannedPhase:
    name: str
    intent: str
    energy_target: float
    tracks: tuple[PlannedTrack, ...]


@dataclass(frozen=True)
class PlannedJourney:
    title: str
    summary: str
    explanation: str
    phases: tuple[PlannedPhase, ...]


class GeminiMusicResearcher:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        opener: Callable[..., object] = urlopen,
    ) -> None:
        self.api_key = api_key if api_key is not None else (
            os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
        self.model = model or os.getenv("GEMINI_MUSIC_MODEL", DEFAULT_MUSIC_MODEL)
        self.opener = opener

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def research(self, tracks: list[dict[str, str]]) -> list[MusicProfile]:
        if not self.enabled:
            raise RuntimeError("GEMINI_API_KEY is not configured")

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
        content = self._generate_text(prompt, temperature=0.1, max_output_tokens=900)

        try:
            parsed = self._parse_json_object(content)
            raw_profiles = parsed["tracks"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Gemini returned an invalid music research response") from exc

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
            raise RuntimeError("Gemini did not return any matching music profiles")
        return profiles

    def plan_journey(
        self,
        *,
        situation: str,
        venue: str,
        start_energy: str,
        end_energy: str,
        discovery: str,
        total_tracks: int,
        feedback: str = "",
    ) -> PlannedJourney:
        if not self.enabled:
            return self.fallback_journey(
                situation=situation,
                venue=venue,
                start_energy=start_energy,
                end_energy=end_energy,
                discovery=discovery,
                total_tracks=total_tracks,
                feedback=feedback,
                note="GEMINI_API_KEY não configurada; usando curadoria local de demonstração.",
            )

        prompt = (
            "Você é um curador musical brasileiro com mentalidade de DJ e pesquisador de tendências. "
            "Crie uma jornada musical do zero para Spotify, não baseada em playlist existente. "
            "Antes de escolher as faixas, faça uma curadoria mental em 3 etapas: "
            "1) interprete o contexto social do briefing; 2) identifique cenas, gêneros e artistas em alta "
            "que combinam com esse contexto; 3) ordene as músicas por progressão de energia, não por gosto solto. "
            "A jornada precisa ter quatro fases: Chegada, Aquecimento, Pico e Fechamento. "
            "Escolha músicas reais, com nomes oficiais, fáceis de encontrar no Spotify no mercado brasileiro. "
            "Use sinais atuais quando disponíveis: Spotify Charts/Top 50/Viral BR e Global, playlists editoriais "
            "e algorítmicas do Spotify, lançamentos recentes, TikTok/Reels, YouTube Music, Billboard Brasil/Hot 100, "
            "rádios/sets de DJs, páginas oficiais de artistas e repertório recorrente de festas reais. "
            "Priorize faixas em circulação em 2025-2026, músicas virais, lançamentos recentes e artistas relevantes "
            "agora quando isso combinar com o briefing. Não force música atual se uma faixa mais antiga funcionar "
            "muito melhor para o momento; nesse caso, explique no reason por que ela entrou. "
            "Evite respostas preguiçosas: não use sempre os mesmos hits globais óbvios, não repita artista demais, "
            "não misture gêneros incompatíveis sem ponte, não coloque música de pico na chegada e não coloque "
            "faixa calma demais no pico. "
            "Para resenha, festa em casa ou Brasil, favoreça repertório brasileiro quando fizer sentido: funk atual, "
            "pop brasileiro, pagode, sertanejo, arrocha/piseiro, trap/rap BR, música latina e hits virais locais. "
            "Para treino, priorize BPM, impacto e constância; para date, priorize clima e textura; para estudo, "
            "priorize baixa distração; para viagem, priorize familiaridade e fluxo. "
            "Preferência de seleção: se for mais_conhecidas, use faixas reconhecíveis e populares; "
            "se for equilibrado, misture hits atuais, faixas conhecidas e boas descobertas; "
            "se for mais_descobertas, use artistas/faixas menos óbvios, mas ainda encontráveis no Spotify. "
            "Cada reason deve citar o sinal de escolha em português: exemplo 'viral recente', 'hit de festa BR', "
            "'ponte de energia', 'clássico necessário', 'lançamento alinhado ao briefing'. "
            "Responda com apenas um objeto JSON puro, sem markdown, sem comentários, sem citações e sem texto antes "
            "ou depois. O formato obrigatório é: "
            '{"title":"","summary":"","explanation":"","phases":[{"name":"","intent":"",'
            '"energy_target":0.5,"tracks":[{"title":"","artist":"","energy":0.5,'
            '"danceability":0.5,"bpm":120,"genre":"","reason":"","search_query":""}]}]}. '
            "Cada search_query deve ser curta e exata, no formato titulo artista, usando nomes oficiais do Spotify. "
            "Evite remix, live, sped up, slowed, karaoke, cover ou versão alternativa, salvo quando essa versão for "
            "explicitamente a mais popular ou pedida pelo contexto. "
            "Use exatamente o total de músicas solicitado, distribuído entre as quatro fases. "
            "A explicação deve ser breve, com no máximo 2 frases, dizendo por que essa curadoria combina com "
            "o briefing e como a energia evolui.\n\n"
            f"Situação: {situation}\n"
            f"Lugar/uso: {venue}\n"
            f"Começar: {start_energy}\n"
            f"Terminar: {end_energy}\n"
            f"Preferência de seleção: {discovery}\n"
            f"Total de músicas: {total_tracks}\n"
            f"Feedback de ajuste: {feedback or 'nenhum'}"
        )
        content = self._generate_text(prompt, temperature=0.55, max_output_tokens=2400)

        try:
            parsed = self._parse_json_object(content)
            parsed = self._normalize_journey_payload(parsed)
            phases = parsed["phases"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            preview = str(content)[:240]
            raise RuntimeError(f"Gemini returned an invalid journey response: {preview}") from exc

        planned_phases: list[PlannedPhase] = []
        for raw_phase in phases[:4]:
            raw_tracks = raw_phase.get("tracks") or []
            tracks = tuple(
                PlannedTrack(
                    title=str(item.get("title") or "")[:160],
                    artist=str(item.get("artist") or "")[:160],
                    energy=self._bounded_float(item.get("energy", 0.5)),
                    danceability=self._bounded_float(item.get("danceability", 0.5)),
                    bpm=self._nullable_bpm(item.get("bpm")),
                    genre=str(item.get("genre") or "desconhecido")[:80],
                    reason=str(item.get("reason") or "Escolhida para a progressão.")[:220],
                    search_query=str(
                        item.get("search_query")
                        or f"{item.get('title', '')} {item.get('artist', '')}"
                    )[:240],
                )
                for item in raw_tracks
                if item.get("title") and item.get("artist")
            )
            planned_phases.append(
                PlannedPhase(
                    name=str(raw_phase.get("name") or "Bloco")[:80],
                    intent=str(raw_phase.get("intent") or "Parte da jornada musical.")[:260],
                    energy_target=self._bounded_float(raw_phase.get("energy_target", 0.5)),
                    tracks=tracks,
                )
            )
        if not planned_phases or not any(phase.tracks for phase in planned_phases):
            raise RuntimeError("Gemini did not return usable journey tracks")
        return PlannedJourney(
            title=str(parsed.get("title") or "Jornada musical")[:120],
            summary=str(parsed.get("summary") or situation or "Playlist gerada por IA.")[:260],
            explanation=str(parsed.get("explanation") or "Sequência organizada em quatro fases.")[:700],
            phases=tuple(planned_phases),
        )

    def fallback_journey(
        self,
        *,
        situation: str,
        venue: str,
        start_energy: str,
        end_energy: str,
        discovery: str,
        total_tracks: int,
        feedback: str = "",
        note: str = "Gemini indisponível; usando curadoria local de demonstração.",
    ) -> PlannedJourney:
        pool = self._fallback_pool(venue, discovery, feedback)
        context = self._build_context(
            situation=situation,
            venue=venue,
            start_energy=start_energy,
            end_energy=end_energy,
            discovery=discovery,
            feedback=feedback,
        )
        counts = self._phase_counts(total_tracks)
        phase_specs = (
            ("Chegada", "Abrir com faixas acessíveis e energia controlada.", 0.32, 0.6),
            ("Aquecimento", "Subir ritmo e familiaridade sem antecipar o pico.", 0.55, 0.78),
            ("Pico", "Concentrar músicas mais fortes e dançantes.", 0.84, 0.9),
            ("Fechamento", "Manter a vibe e pousar sem queda brusca.", 0.62 if end_energy != "mais_calmo" else 0.38, 0.65 if end_energy != "mais_calmo" else 0.45),
        )
        phases: list[PlannedPhase] = []
        used_tracks: set[tuple[str, str]] = set()
        for phase_index, (phase_name, intent, target_energy, target_danceability) in enumerate(phase_specs):
            tracks: list[PlannedTrack] = []
            ranked_pool = self._rank_fallback_pool(
                pool,
                context=context,
                phase_name=phase_name,
                target_energy=target_energy,
                target_danceability=target_danceability,
            )
            for item in ranked_pool:
                key = (str(item["title"]).lower(), str(item["artist"]).lower())
                if key in used_tracks:
                    continue
                used_tracks.add(key)
                tracks.append(
                    PlannedTrack(
                        title=item["title"],
                        artist=item["artist"],
                        energy=item["energy"],
                        danceability=item["danceability"],
                        bpm=item["bpm"],
                        genre=item["genre"],
                        reason=self._phase_reason(phase_name, context, item),
                        search_query=f"{item['title']} {item['artist']}",
                    )
                )
                if len(tracks) >= counts[phase_index]:
                    break
            if len(tracks) < counts[phase_index]:
                for item in ranked_pool:
                    key = (str(item["title"]).lower(), str(item["artist"]).lower())
                    if key in used_tracks:
                        continue
                    used_tracks.add(key)
                    tracks.append(
                        PlannedTrack(
                            title=item["title"],
                            artist=item["artist"],
                            energy=item["energy"],
                            danceability=item["danceability"],
                            bpm=item["bpm"],
                            genre=item["genre"],
                            reason=self._phase_reason(phase_name, context, item),
                            search_query=f"{item['title']} {item['artist']}",
                        )
                    )
                    if len(tracks) >= counts[phase_index]:
                        break
            phases.append(
                PlannedPhase(
                    name=phase_name,
                    intent=intent,
                    energy_target=target_energy,
                    tracks=tuple(tracks),
                )
            )
        title = "Jornada musical gerada"
        if venue == "resenha":
            title = "Resenha que cresce"
        elif venue == "treino":
            title = "Treino em progressão"
        elif venue == "date":
            title = "Date com clima crescente"
        return PlannedJourney(
            title=title,
            summary=situation[:260] or "Playlist nova organizada em quatro fases.",
            explanation=(
                f"{note} A ordem foi montada para começar em {start_energy}, chegar em {end_energy} "
                "e manter uma progressão editável por feedback."
            )[:700],
            phases=tuple(phases),
        )

    @staticmethod
    def _build_context(
        *,
        situation: str,
        venue: str,
        start_energy: str,
        end_energy: str,
        discovery: str,
        feedback: str,
    ) -> dict[str, bool]:
        text = " ".join(
            [situation, venue, start_energy, end_energy, discovery, feedback]
        ).lower()
        return {
            "romantic": any(keyword in text for keyword in ["romant", "date", "casal", "clima", "suave", "chill", "calmo"]),
            "brazilian": any(keyword in text for keyword in ["brasil", "brasileiro", "funk", "pagode", "sertanejo", "arrocha", "piseiro", "baiana", "festa"]),
            "party": any(keyword in text for keyword in ["festa", "dance", "dançar", "animado", "pico", "energia"]),
            "workout": any(keyword in text for keyword in ["treino", "workout", "academia", "corrida", "musculação"]),
            "study": any(keyword in text for keyword in ["estudo", "focus", "concentr", "trabalho"]),
            "travel": any(keyword in text for keyword in ["viagem", "road", "viaj"]),
            "discovery": discovery == "mais_descobertas",
        }

    def _rank_fallback_pool(
        self,
        pool: list[dict],
        *,
        context: dict[str, bool],
        phase_name: str,
        target_energy: float,
        target_danceability: float,
    ) -> list[dict]:
        ranked: list[tuple[float, dict]] = []
        for item in pool:
            score = self._score_fallback_track(
                item,
                context=context,
                phase_name=phase_name,
                target_energy=target_energy,
                target_danceability=target_danceability,
            )
            ranked.append((score, item))
        ranked.sort(key=lambda entry: (-entry[0], str(entry[1]["title"]).lower()))
        return [item for _, item in ranked]

    def _score_fallback_track(
        self,
        item: dict,
        *,
        context: dict[str, bool],
        phase_name: str,
        target_energy: float,
        target_danceability: float,
    ) -> float:
        energy_gap = abs(float(item["energy"]) - target_energy)
        dance_gap = abs(float(item["danceability"]) - target_danceability)
        score = 1.2 - (energy_gap * 1.4) - (dance_gap * 1.0)

        if phase_name == "Pico":
            score += 0.35 if float(item["energy"]) >= 0.8 else 0.0
            score += 0.2 if float(item["danceability"]) >= 0.8 else 0.0
        elif phase_name == "Chegada":
            score += 0.25 if float(item["energy"]) <= 0.55 else 0.0
            score += 0.15 if float(item["danceability"]) >= 0.7 else 0.0
        elif phase_name == "Aquecimento":
            score += 0.2 if 0.5 <= float(item["energy"]) <= 0.75 else 0.0
            score += 0.1 if float(item["danceability"]) >= 0.7 else 0.0
        elif phase_name == "Fechamento":
            score += 0.2 if float(item["energy"]) <= 0.7 else 0.0
            score += 0.1 if float(item["danceability"]) >= 0.6 else 0.0

        if context["romantic"]:
            if str(item["genre"]).lower() in {"mpb", "indie pop", "pop brasileiro", "pop rock", "disco"}:
                score += 0.45
            if phase_name in {"Chegada", "Aquecimento"} and float(item["energy"]) <= 0.65:
                score += 0.1
        if context["brazilian"]:
            if str(item["genre"]).lower() in {"indie pop", "mpb", "pop brasileiro", "funk", "pagode", "pagodão baiano", "funk pop", "pop funk", "axé pop", "manguebeat"}:
                score += 0.35
        if context["party"]:
            if phase_name == "Pico" and float(item["energy"]) >= 0.8:
                score += 0.3
            if phase_name != "Pico" and float(item["danceability"]) >= 0.75:
                score += 0.1
        if context["workout"]:
            if float(item["energy"]) >= 0.75:
                score += 0.2
        if context["study"]:
            if float(item["energy"]) <= 0.55 and float(item["danceability"]) <= 0.75:
                score += 0.2
        if context["travel"]:
            if str(item["genre"]).lower() in {"pop", "dance pop", "disco pop", "house"}:
                score += 0.15
        if context["discovery"]:
            score += 0.05
        return score

    @staticmethod
    def _phase_reason(phase_name: str, context: dict[str, bool], item: dict) -> str:
        reason_parts = [f"Faixa escolhida para {phase_name.lower()} por combinar com o briefing."]
        if context["romantic"]:
            reason_parts.append("tom mais acolhedor")
        if context["party"]:
            reason_parts.append("impacto de pista")
        if context["workout"]:
            reason_parts.append("ritmo e intensidade")
        if context["study"]:
            reason_parts.append("menor distração")
        if context["travel"]:
            reason_parts.append("fluxo de viagem")
        return "; ".join(reason_parts)[:220]

    @staticmethod
    def _phase_counts(total_tracks: int) -> tuple[int, int, int, int]:
        total = max(8, min(40, total_tracks))
        counts = [max(1, int(total * weight)) for weight in (0.22, 0.28, 0.34, 0.16)]
        while sum(counts) < total:
            counts[2] += 1
        while sum(counts) > total:
            counts[max(range(4), key=lambda index: counts[index])] -= 1
        return counts[0], counts[1], counts[2], counts[3]

    @staticmethod
    def _fallback_pool(venue: str, discovery: str, feedback: str) -> list[dict]:
        brazilian = [
            {"title": "Acorda Pedrinho", "artist": "Jovem Dionisio", "energy": 0.45, "danceability": 0.72, "bpm": 120, "genre": "indie pop"},
            {"title": "Pilantra", "artist": "Jão, Anitta", "energy": 0.7, "danceability": 0.76, "bpm": 118, "genre": "pop brasileiro"},
            {"title": "Malvadão 3", "artist": "Xamã, Gustah, Neo Beats", "energy": 0.76, "danceability": 0.8, "bpm": 130, "genre": "trap funk"},
            {"title": "Dentro da Hilux", "artist": "Luan Pereira, MC Daniel, MC Ryan SP", "energy": 0.78, "danceability": 0.82, "bpm": 130, "genre": "funknejo"},
            {"title": "Zona de Perigo", "artist": "Léo Santana", "energy": 0.86, "danceability": 0.9, "bpm": 150, "genre": "pagodão baiano"},
            {"title": "Macetando", "artist": "Ivete Sangalo, Ludmilla", "energy": 0.88, "danceability": 0.86, "bpm": 135, "genre": "axé pop"},
            {"title": "Meu Esquema", "artist": "Mundo Livre S/A", "energy": 0.48, "danceability": 0.68, "bpm": 103, "genre": "manguebeat"},
            {"title": "Toda Menina Baiana", "artist": "Gilberto Gil", "energy": 0.55, "danceability": 0.74, "bpm": 108, "genre": "mpb"},
            {"title": "Baile de Favela", "artist": "MC João", "energy": 0.82, "danceability": 0.88, "bpm": 130, "genre": "funk"},
            {"title": "Cheguei", "artist": "Ludmilla", "energy": 0.86, "danceability": 0.82, "bpm": 130, "genre": "pop funk"},
            {"title": "Vai Malandra", "artist": "Anitta", "energy": 0.88, "danceability": 0.9, "bpm": 100, "genre": "funk pop"},
            {"title": "Bola Rebola", "artist": "Tropkillaz", "energy": 0.84, "danceability": 0.89, "bpm": 95, "genre": "funk pop"},
            {"title": "Deixa Acontecer", "artist": "Grupo Revelação", "energy": 0.58, "danceability": 0.76, "bpm": 96, "genre": "pagode"},
        ]
        global_pop = [
            {"title": "Espresso", "artist": "Sabrina Carpenter", "energy": 0.72, "danceability": 0.82, "bpm": 104, "genre": "pop"},
            {"title": "Training Season", "artist": "Dua Lipa", "energy": 0.78, "danceability": 0.81, "bpm": 123, "genre": "dance pop"},
            {"title": "Beautiful Things", "artist": "Benson Boone", "energy": 0.68, "danceability": 0.47, "bpm": 105, "genre": "pop rock"},
            {"title": "greedy", "artist": "Tate McRae", "energy": 0.74, "danceability": 0.75, "bpm": 111, "genre": "pop"},
            {"title": "Levitating", "artist": "Dua Lipa", "energy": 0.74, "danceability": 0.88, "bpm": 103, "genre": "pop"},
            {"title": "Get Lucky", "artist": "Daft Punk", "energy": 0.66, "danceability": 0.81, "bpm": 116, "genre": "disco pop"},
            {"title": "Blinding Lights", "artist": "The Weeknd", "energy": 0.82, "danceability": 0.72, "bpm": 171, "genre": "synth pop"},
            {"title": "One More Time", "artist": "Daft Punk", "energy": 0.87, "danceability": 0.74, "bpm": 123, "genre": "house"},
            {"title": "Titanium", "artist": "David Guetta", "energy": 0.88, "danceability": 0.6, "bpm": 126, "genre": "edm"},
            {"title": "Rather Be", "artist": "Clean Bandit", "energy": 0.7, "danceability": 0.8, "bpm": 121, "genre": "dance pop"},
            {"title": "September", "artist": "Earth Wind & Fire", "energy": 0.68, "danceability": 0.7, "bpm": 126, "genre": "disco"},
            {"title": "Adventure of a Lifetime", "artist": "Coldplay", "energy": 0.62, "danceability": 0.64, "bpm": 112, "genre": "pop rock"},
        ]
        workout = [
            {"title": "Stronger", "artist": "Kanye West", "energy": 0.82, "danceability": 0.62, "bpm": 104, "genre": "hip hop"},
            {"title": "Turn Down for What", "artist": "DJ Snake", "energy": 0.95, "danceability": 0.82, "bpm": 100, "genre": "trap"},
            {"title": "Don't Start Now", "artist": "Dua Lipa", "energy": 0.76, "danceability": 0.79, "bpm": 124, "genre": "dance pop"},
            {"title": "Levels", "artist": "Avicii", "energy": 0.9, "danceability": 0.6, "bpm": 126, "genre": "edm"},
        ]
        use_brazil = venue in {"resenha", "festa"} or "funk" in feedback.lower() or "brasil" in feedback.lower()
        pool = (brazilian + global_pop) if use_brazil else (global_pop + brazilian)
        if venue == "treino":
            pool = workout + pool
        if discovery == "mais_descobertas":
            pool = list(reversed(pool))
        return pool

    def _generate_text(self, prompt: str, *, temperature: float, max_output_tokens: int) -> str:
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        request = Request(
            f"{GEMINI_API_URL.format(model=quote(self.model, safe=''))}?key={quote(self.api_key or '', safe='')}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "journey-dj/3.0",
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
            raise RuntimeError(f"Gemini music request failed: {message}") from exc

        try:
            candidate = payload["candidates"][0]
            parts = candidate["content"]["parts"]
            content = "".join(str(part.get("text", "")) for part in parts).strip()
        except (KeyError, IndexError, TypeError) as exc:
            block_reason = payload.get("promptFeedback", {}).get("blockReason")
            message = f" Gemini bloqueou a resposta: {block_reason}." if block_reason else ""
            raise RuntimeError(f"Gemini returned an invalid response.{message}") from exc
        if not content:
            finish_reason = candidate.get("finishReason")
            raise RuntimeError(f"Gemini returned an empty response: {finish_reason or 'sem motivo'}")
        return content

    @staticmethod
    def _parse_json_object(content: str) -> dict:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed
        except json.JSONDecodeError:
            start = cleaned.find("{")
            if start < 0:
                raise
            depth = 0
            in_string = False
            escaped = False
            for index, character in enumerate(cleaned[start:], start=start):
                if escaped:
                    escaped = False
                    continue
                if character == "\\":
                    escaped = True
                    continue
                if character == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if character == "{":
                    depth += 1
                elif character == "}":
                    depth -= 1
                    if depth == 0:
                        return json.loads(cleaned[start : index + 1])
            raise

    @staticmethod
    def _normalize_journey_payload(parsed: object) -> dict:
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if not isinstance(parsed, dict):
            raise TypeError("Journey payload must be an object")

        if "phases" not in parsed:
            for key in ("blocks", "blocos", "sections", "playlist"):
                value = parsed.get(key)
                if isinstance(value, list):
                    parsed["phases"] = value
                    break

        phases = parsed.get("phases")
        if not isinstance(phases, list):
            raise KeyError("phases")

        normalized_phases = []
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                continue
            tracks = (
                phase.get("tracks")
                or phase.get("songs")
                or phase.get("musicas")
                or phase.get("faixas")
                or []
            )
            phase["tracks"] = tracks
            phase.setdefault("name", phase.get("title") or phase.get("nome") or f"Bloco {index + 1}")
            phase.setdefault("intent", phase.get("description") or phase.get("descricao") or "Parte da playlist.")
            phase.setdefault("energy_target", phase.get("energy") or phase.get("energia") or 0.5)
            normalized_tracks = []
            for item in tracks:
                if not isinstance(item, dict):
                    continue
                item.setdefault("title", item.get("name") or item.get("track") or item.get("musica"))
                item.setdefault("artist", item.get("artists") or item.get("artista") or item.get("artist_name"))
                item.setdefault("search_query", f"{item.get('title', '')} {item.get('artist', '')}".strip())
                item.setdefault("genre", item.get("genero") or "desconhecido")
                item.setdefault("reason", item.get("motivo") or "Escolhida para a playlist.")
                item.setdefault("energy", item.get("energia") or 0.5)
                item.setdefault("danceability", item.get("dancabilidade") or 0.6)
                normalized_tracks.append(item)
            phase["tracks"] = normalized_tracks
            normalized_phases.append(phase)
        parsed["phases"] = normalized_phases
        return parsed

    @staticmethod
    def _bounded_float(value: object) -> float:
        return round(max(0.0, min(1.0, float(value))), 3)

    @staticmethod
    def _nullable_bpm(value: object) -> int | None:
        if value is None:
            return None
        bpm = int(round(float(value)))
        return max(40, min(240, bpm))


GroqMusicResearcher = GeminiMusicResearcher
