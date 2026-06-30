import {
  CheckCircle2,
  Loader2,
  MessageSquareText,
  Music2,
  Send,
  Sparkles,
  SkipBack,
  SkipForward,
  Wand2,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

const TOKEN_KEY = "journey-dj-spotify-token";
const VERIFIER_KEY = "journey-dj-pkce-verifier";
const AUTH_STATE_KEY = "journey-dj-auth-state";
const REQUESTED_SPOTIFY_SCOPES: string[] = [];

type Venue = "resenha" | "festa" | "treino" | "viagem" | "date" | "estudo" | "sozinho";
type StartEnergy = "calmo" | "medio" | "animado";
type EndEnergy = "mais_intenso" | "no_pico" | "mais_calmo";
type Discovery = "equilibrado" | "mais_conhecidas" | "mais_descobertas";

type AppConfig = {
  spotify_client_id: string | null;
  groq_enabled: boolean;
  ai_provider?: string;
  ai_model?: string;
  ai_key_fingerprint?: string | null;
  vision_interval_seconds: number;
  min_track_seconds: number;
};

type PlannedTrack = {
  title: string;
  artist: string;
  genre: string;
  bpm?: number | null;
  energy: number;
  danceability: number;
  reason?: string;
  search_query: string;
};

type ResolvedTrack = PlannedTrack & {
  spotifyId: string;
  uri: string;
  name: string;
  artists: string;
  externalUrl: string;
  imageUrl: string;
};

type JourneyPhase<TTrack = PlannedTrack> = {
  name: string;
  intent: string;
  energy_target: number;
  tracks: TTrack[];
};

type JourneyPlan<TTrack = PlannedTrack> = {
  title: string;
  summary: string;
  explanation: string;
  phases: JourneyPhase<TTrack>[];
};

type SpotifyToken = {
  access_token: string;
  token_type: string;
  expires_in: number;
  expires_at: number;
  refresh_token?: string;
  scope?: string;
};

type SpotifyTrack = {
  id: string;
  uri: string;
  name: string;
  artists: { name: string }[];
  popularity?: number;
  external_urls?: { spotify?: string };
  album?: { images?: { url: string }[]; name?: string; release_date?: string };
};

type ChatMessage = {
  id: number;
  role: "assistant" | "user";
  text: string;
};

type EventItem = {
  id: number;
  text: string;
};

class SpotifyApiError extends Error {
  status: number;
  spotifyMessage: string;

  constructor(status: number, spotifyMessage: string) {
    super(spotifyMessage);
    this.name = "SpotifyApiError";
    this.status = status;
    this.spotifyMessage = spotifyMessage;
  }
}

const venueLabels: Record<Venue, string> = {
  resenha: "Resenha",
  festa: "Festa",
  treino: "Treino",
  viagem: "Viagem",
  date: "Date",
  estudo: "Estudo",
  sozinho: "Sozinho",
};

const startLabels: Record<StartEnergy, string> = {
  calmo: "Calmo",
  medio: "Médio",
  animado: "Animado",
};

const endLabels: Record<EndEnergy, string> = {
  mais_intenso: "Mais intenso",
  no_pico: "No pico",
  mais_calmo: "Mais calmo",
};

const discoveryLabels: Record<Discovery, string> = {
  equilibrado: "Equilibrada",
  mais_conhecidas: "Mais conhecidas",
  mais_descobertas: "Mais descobertas",
};

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = await response.text();
    try {
      const parsed = JSON.parse(detail) as { detail?: string };
      detail = parsed.detail || detail;
    } catch {
      // Keep response text.
    }
    throw new Error(detail || `Erro HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function tracksForDuration(minutes: number): number {
  return Math.max(8, Math.min(40, Math.round(minutes / 3.5)));
}

function normalize(value: string): string {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function shortText(value: string, max = 260): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 3)}...`;
}

function energyTag(energy: number): string {
  if (energy < 0.38) return "calma";
  if (energy < 0.68) return "média";
  if (energy < 0.84) return "agitada";
  return "pico";
}

function danceTag(danceability: number): string {
  if (danceability < 0.45) return "menos dançante";
  if (danceability < 0.72) return "groove";
  return "dançante";
}

function bpmTag(bpm?: number | null): string {
  if (!bpm) return "BPM estimado";
  if (bpm < 95) return `${bpm} BPM`;
  if (bpm < 120) return `${bpm} BPM`;
  return `${bpm} BPM`;
}

function randomString(length = 64): string {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from(bytes, (byte) => alphabet[byte % alphabet.length]).join("");
}

function base64Url(buffer: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function spotifyRedirectUri(): string {
  return `${window.location.origin}${window.location.pathname}`;
}

function hasRequiredSpotifyScopes(token: SpotifyToken | null): boolean {
  return Boolean(token);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function spotifyErrorFromResponse(response: Response): Promise<SpotifyApiError> {
  const body = await response.text();
  try {
    const parsed = JSON.parse(body) as { error?: { status?: number; message?: string } };
    return new SpotifyApiError(
      parsed.error?.status || response.status,
      parsed.error?.message || body || `Spotify HTTP ${response.status}`
    );
  } catch {
    return new SpotifyApiError(response.status, body || `Spotify HTTP ${response.status}`);
  }
}

export function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [spotifyToken, setSpotifyToken] = useState<SpotifyToken | null>(null);
  const [situation, setSituation] = useState(
    "Vou reunir uns amigos em casa, quero começar leve e depois subir para uma vibe dançante sem ficar pesado demais."
  );
  const [venue, setVenue] = useState<Venue>("resenha");
  const [startEnergy, setStartEnergy] = useState<StartEnergy>("calmo");
  const [endEnergy, setEndEnergy] = useState<EndEnergy>("mais_intenso");
  const [discovery, setDiscovery] = useState<Discovery>("equilibrado");
  const [duration, setDuration] = useState(45);
  const [feedback, setFeedback] = useState("");
  const [journey, setJourney] = useState<JourneyPlan<ResolvedTrack> | null>(null);
  const [currentTrackIndex, setCurrentTrackIndex] = useState(0);
  const [needsSpotifyReconnect, setNeedsSpotifyReconnect] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [chat, setChat] = useState<ChatMessage[]>([
    {
      id: 1,
      role: "assistant",
      text:
        "Me passa o contexto, escolhe a duração e eu monto uma fila local com músicas do Spotify. Depois você pode mandar feedbacks para eu ajustar a curadoria.",
    },
  ]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const tracks = useMemo(
    () => journey?.phases.flatMap((phase) => phase.tracks) || [],
    [journey]
  );

  const canGenerate = Boolean(spotifyToken && config?.spotify_client_id && !busy);
  const currentTrack = tracks[currentTrackIndex] || null;
  const canUseQueue = Boolean(tracks.length && !busy);
  const trackEmbedUrl = currentTrack
    ? `https://open.spotify.com/embed/track/${currentTrack.spotifyId}?utm_source=generator&theme=0`
    : "";

  const pushEvent = useCallback((text: string) => {
    setEvents((current) =>
      [
        { id: Date.now() + Math.random(), text: `${new Date().toLocaleTimeString("pt-BR")} · ${text}` },
        ...current,
      ].slice(0, 8)
    );
  }, []);

  const appendChat = useCallback((role: "assistant" | "user", text: string) => {
    const clean = text.replace(/\s+/g, " ").trim();
    if (!clean) return;
    setChat((current) => [...current, { id: Date.now() + Math.random(), role, text: clean }]);
  }, []);

  const showError = useCallback(
    (error: unknown) => {
      let message = error instanceof Error ? error.message : String(error);
      if (error instanceof SpotifyApiError && error.status === 429) {
        message = "O Spotify limitou as buscas por alguns segundos. O Gemini já gerou a curadoria; espera um pouco e tenta de novo.";
      } else if (message.toLowerCase().includes("too many requests")) {
        message = "A API limitou as requisições por alguns segundos. Espera um pouco e tenta gerar de novo.";
      }
      pushEvent(message);
      appendChat("assistant", `Deu erro: ${message}`);
    },
    [appendChat, pushEvent]
  );

  const saveSpotifyToken = useCallback((token: SpotifyToken) => {
    const nextToken: SpotifyToken = {
      ...token,
      expires_at: Date.now() + token.expires_in * 1000,
      refresh_token: token.refresh_token || spotifyToken?.refresh_token,
      scope: token.scope || spotifyToken?.scope || "",
    };
    console.info("Spotify scopes:", nextToken.scope || "(sem scope retornado)");
    setNeedsSpotifyReconnect(false);
    setSpotifyToken(nextToken);
    sessionStorage.setItem(TOKEN_KEY, JSON.stringify(nextToken));
    return nextToken;
  }, [spotifyToken?.refresh_token]);

  const refreshSpotifyToken = useCallback(async () => {
    if (!spotifyToken?.refresh_token || !config?.spotify_client_id) {
      throw new Error("Reconecte o Spotify");
    }
    const response = await fetch("https://accounts.spotify.com/api/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: config.spotify_client_id,
        grant_type: "refresh_token",
        refresh_token: spotifyToken.refresh_token,
      }),
    });
    if (!response.ok) throw new Error("A sessão do Spotify expirou");
    const refreshedToken = (await response.json()) as SpotifyToken;
    console.info("Spotify refresh scopes:", refreshedToken.scope || spotifyToken.scope || "(sem scope retornado)");
    return saveSpotifyToken(refreshedToken);
  }, [config?.spotify_client_id, saveSpotifyToken, spotifyToken?.refresh_token]);

  const spotifyFetch = useCallback(
    async <T,>(path: string, options: RequestInit = {}, retry = true, rateRetries = 2): Promise<T> => {
      let token = spotifyToken;
      if (!token) throw new Error("Conecte o Spotify primeiro");
      if (Date.now() >= token.expires_at - 30000) {
        token = await refreshSpotifyToken();
      }
      const response = await fetch(`https://api.spotify.com/v1${path}`, {
        ...options,
        headers: {
          Authorization: `Bearer ${token.access_token}`,
          "Content-Type": "application/json",
          ...(options.headers || {}),
        },
      });
      if (response.status === 401 && retry) {
        await refreshSpotifyToken();
        return spotifyFetch<T>(path, options, false, rateRetries);
      }
      if (response.status === 429 && rateRetries > 0) {
        const retryAfter = Number(response.headers.get("Retry-After") || "1");
        const waitMs = Math.max(1200, Math.min(8000, retryAfter * 1000 + 350));
        setStatus(`Spotify pediu uma pausa rápida... tentando de novo em ${Math.ceil(waitMs / 1000)}s`);
        await sleep(waitMs);
        return spotifyFetch<T>(path, options, retry, rateRetries - 1);
      }
      if (!response.ok) {
        throw await spotifyErrorFromResponse(response);
      }
      if (response.status === 204) return null as T;
      return response.json() as Promise<T>;
    },
    [refreshSpotifyToken, spotifyToken]
  );

  const handleSpotifyCallback = useCallback(async () => {
    if (!config?.spotify_client_id) return;
    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get("error");
    if (oauthError) {
      history.replaceState({}, document.title, window.location.pathname);
      throw new Error(`Spotify recusou a conexão: ${oauthError}`);
    }
    const code = params.get("code");
    if (!code) return;
    if (params.get("state") !== sessionStorage.getItem(AUTH_STATE_KEY)) {
      throw new Error("Estado OAuth do Spotify não confere");
    }
    const verifier = sessionStorage.getItem(VERIFIER_KEY);
    if (!verifier) throw new Error("Código PKCE não encontrado");
    const response = await fetch("https://accounts.spotify.com/api/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: config.spotify_client_id,
        grant_type: "authorization_code",
        code,
        redirect_uri: spotifyRedirectUri(),
        code_verifier: verifier,
      }),
    });
    if (!response.ok) throw new Error(`Login Spotify falhou: ${await response.text()}`);
    const tokenData = (await response.json()) as SpotifyToken;
    console.info("Spotify callback scopes:", tokenData.scope || "(sem scope retornado)");
    saveSpotifyToken(tokenData);
    sessionStorage.removeItem(VERIFIER_KEY);
    sessionStorage.removeItem(AUTH_STATE_KEY);
    history.replaceState({}, document.title, window.location.pathname);
  }, [config?.spotify_client_id, saveSpotifyToken]);

  const connectSpotify = useCallback(async () => {
    if (!config?.spotify_client_id) throw new Error("Defina SPOTIFY_CLIENT_ID no backend");
    sessionStorage.removeItem(TOKEN_KEY);
    setSpotifyToken(null);
    const verifier = randomString();
    const challenge = base64Url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
    const authState = randomString(24);
    sessionStorage.setItem(VERIFIER_KEY, verifier);
    sessionStorage.setItem(AUTH_STATE_KEY, authState);
    const params = new URLSearchParams({
      client_id: config.spotify_client_id,
      response_type: "code",
      redirect_uri: spotifyRedirectUri(),
      code_challenge_method: "S256",
      code_challenge: challenge,
      state: authState,
      show_dialog: "true",
    });
    if (REQUESTED_SPOTIFY_SCOPES.length) {
      params.set("scope", REQUESTED_SPOTIFY_SCOPES.join(" "));
    }
    window.location.assign(`https://accounts.spotify.com/authorize?${params}`);
  }, [config?.spotify_client_id]);

  const scoreSpotifyCandidate = useCallback((track: SpotifyTrack, planned: PlannedTrack) => {
    const title = normalize(planned.title);
    const artist = normalize(planned.artist);
    const candidateTitle = normalize(track.name);
    const candidateArtists = track.artists.map((item) => normalize(item.name)).join(" ");
    const albumName = normalize(track.album?.name || "");
    const plannedText = normalize(`${planned.title} ${planned.artist} ${planned.genre} ${planned.search_query}`);
    const versionWords = ["remix", "live", "sped up", "slowed", "karaoke", "cover", "instrumental", "acoustic"];
    let score = 0;
    if (candidateTitle === title) score += 80;
    else if (candidateTitle.includes(title) || title.includes(candidateTitle)) score += 52;
    else if (title.split(" ").some((word) => word.length > 3 && candidateTitle.includes(word))) score += 18;
    if (candidateArtists.includes(artist) || artist.includes(candidateArtists)) score += 70;
    else if (artist.split(" ").some((word) => word.length > 2 && candidateArtists.includes(word))) score += 26;
    score += Math.min(24, (track.popularity || 0) / 4);
    const releaseYear = Number(track.album?.release_date?.slice(0, 4));
    if (releaseYear >= 2025) score += 14;
    else if (releaseYear >= 2023) score += 9;
    else if (releaseYear >= 2020) score += 4;
    for (const word of versionWords) {
      if (!plannedText.includes(word) && (candidateTitle.includes(word) || albumName.includes(word))) {
        score -= 28;
      }
    }
    if (candidateTitle.includes("remaster") && !plannedText.includes("remaster")) score -= 12;
    return score;
  }, []);

  const searchSpotifyTrack = useCallback(
    async (planned: PlannedTrack, usedIds: Set<string>): Promise<SpotifyTrack | null> => {
      const primarySearches = [
        `track:${planned.title} artist:${planned.artist}`,
        planned.search_query,
      ];
      const fallbackSearches = [
        `${planned.title} ${planned.artist}`,
        `${planned.title} ${planned.artist} official`,
        `${planned.search_query} Brasil`,
        `${planned.title} ${planned.artist} ${planned.genre}`,
        `${planned.artist} ${planned.genre}`,
      ];
      const candidates = new Map<string, SpotifyTrack>();
      const bestCandidate = () =>
        [...candidates.values()].sort(
          (left, right) => scoreSpotifyCandidate(right, planned) - scoreSpotifyCandidate(left, planned)
        )[0] || null;
      const strongEnough = (track: SpotifyTrack | null) =>
        Boolean(track && scoreSpotifyCandidate(track, planned) >= 138);
      const runSearches = async (searches: string[], limit: number) => {
        for (const search of searches) {
          const data = await spotifyFetch<{ tracks: { items: SpotifyTrack[] } }>(
            `/search?type=track&limit=${limit}&market=BR&q=${encodeURIComponent(search)}`
          );
          data.tracks.items.forEach((track) => {
            if (!usedIds.has(track.id)) candidates.set(track.id, track);
          });
          const best = bestCandidate();
          if (strongEnough(best)) return best;
        }
        return null;
      };

      const primaryMatch = await runSearches(primarySearches, 5);
      if (primaryMatch) return primaryMatch;

      const fallbackMatch = await runSearches(fallbackSearches, 4);
      return fallbackMatch || bestCandidate();
    },
    [scoreSpotifyCandidate, spotifyFetch]
  );

  const resolvePlanWithSpotify = useCallback(
    async (plan: JourneyPlan): Promise<JourneyPlan<ResolvedTrack>> => {
      const total = plan.phases.reduce((sum, phase) => sum + phase.tracks.length, 0);
      let done = 0;
      const usedSpotifyIds = new Set<string>();
      const phases: JourneyPhase<ResolvedTrack>[] = [];
      for (const phase of plan.phases) {
        const resolvedTracks: ResolvedTrack[] = [];
        for (const planned of phase.tracks) {
          const spotifyTrack = await searchSpotifyTrack(planned, usedSpotifyIds);
          if (spotifyTrack) {
            usedSpotifyIds.add(spotifyTrack.id);
            resolvedTracks.push({
              ...planned,
              spotifyId: spotifyTrack.id,
              uri: spotifyTrack.uri,
              name: spotifyTrack.name,
              artists: spotifyTrack.artists.map((artist) => artist.name).join(", "),
              externalUrl: spotifyTrack.external_urls?.spotify || `https://open.spotify.com/track/${spotifyTrack.id}`,
              imageUrl: spotifyTrack.album?.images?.at(-1)?.url || "",
            });
          } else {
            pushEvent(`Não encontrei no Spotify: ${planned.title} — ${planned.artist}`);
          }
          done += 1;
          setStatus(`Encontrando faixas no Spotify... ${done}/${total}`);
          setProgress(Math.round((done / total) * 100));
          if (done < total) {
            await sleep(220);
          }
        }
        phases.push({ ...phase, tracks: resolvedTracks });
      }
      if (!phases.some((phase) => phase.tracks.length)) {
        throw new Error("A IA sugeriu músicas, mas nenhuma foi encontrada no Spotify.");
      }
      return { ...plan, phases };
    },
    [pushEvent, searchSpotifyTrack]
  );

  const playlistMessage = useCallback(
    (wasFeedback = false, activeJourney = journey) => {
      if (!activeJourney) return "";
      const activeTracks = activeJourney.phases.flatMap((phase) => phase.tracks);
      const opening = wasFeedback ? "Ajustei a playlist" : "Gerei uma playlist";
      const phaseText = activeJourney.phases.map((phase) => phase.name).filter(Boolean).join(", ");
      const base =
        `${opening} de aproximadamente ${duration} min com ${activeTracks.length} músicas. ` +
        `Ela foi pensada para ${venueLabels[venue].toLowerCase()}, começando ${startLabels[
          startEnergy
        ].toLowerCase()} e terminando ${endLabels[endEnergy].toLowerCase()}.`;
      const explanation = shortText(`${activeJourney.summary} ${activeJourney.explanation}`);
      return `${base} ${phaseText ? `O caminho passa por: ${phaseText}. ` : ""}${explanation}`;
    },
    [duration, endEnergy, journey, startEnergy, venue]
  );

  const generateJourney = useCallback(
    async (useFeedback = false) => {
      const cleanFeedback = feedback.trim();
      if (!spotifyToken) throw new Error("Conecte o Spotify para buscar as músicas");
      if (useFeedback && !cleanFeedback) throw new Error("Escreva o que você quer ajustar no feedback");

      appendChat("user", useFeedback ? cleanFeedback : situation || "Gerar uma playlist com essas configurações.");
      setBusy(true);
      setJourney(null);
      setCurrentTrackIndex(0);
      setProgress(0);
      try {
        setStatus("Pedindo uma curadoria atualizada para a IA...");
        const plan = await api<JourneyPlan>("/api/journeys/plan", {
          method: "POST",
          body: JSON.stringify({
            situation,
            venue,
            start_energy: startEnergy,
            end_energy: endEnergy,
            discovery,
            total_tracks: tracksForDuration(duration),
            feedback: useFeedback ? cleanFeedback : "",
          }),
        });
        setStatus("Encontrando as faixas no Spotify...");
        const resolved = await resolvePlanWithSpotify(plan);
        setJourney(resolved);
        appendChat(
          "assistant",
          `${playlistMessage(useFeedback, resolved)} Montei a fila local e carreguei a primeira música no player ao lado.`
        );
        if (useFeedback) setFeedback("");
        pushEvent(useFeedback ? "Fila local reorganizada" : `Fila local gerada: ${resolved.title}`);
      } finally {
        setBusy(false);
        setStatus("");
        setProgress(0);
      }
    },
    [
      appendChat,
      discovery,
      duration,
      endEnergy,
      feedback,
      playlistMessage,
      pushEvent,
      resolvePlanWithSpotify,
      situation,
      spotifyToken,
      startEnergy,
      venue,
    ]
  );

  useEffect(() => {
    api<AppConfig>("/api/config")
      .then((nextConfig) => {
        console.info(
          "AI config:",
          nextConfig.ai_provider || "gemini",
          nextConfig.ai_model || "(modelo padrao)",
          nextConfig.ai_key_fingerprint || "(sem chave)"
        );
        setConfig(nextConfig);
      })
      .catch(showError);
  }, [showError]);

  useEffect(() => {
    if (!config) return;
    const restore = async () => {
      const stored = sessionStorage.getItem(TOKEN_KEY);
      if (stored) {
        try {
          const parsed = JSON.parse(stored) as SpotifyToken;
          if (hasRequiredSpotifyScopes(parsed)) {
            setNeedsSpotifyReconnect(false);
            setSpotifyToken(parsed);
          } else {
            sessionStorage.removeItem(TOKEN_KEY);
            setNeedsSpotifyReconnect(true);
            pushEvent("Reconecte o Spotify para buscar músicas");
          }
        } catch {
          sessionStorage.removeItem(TOKEN_KEY);
        }
      }
      await handleSpotifyCallback();
    };
    restore().catch(showError);
  }, [config, handleSpotifyCallback, pushEvent, showError]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat]);

  const submitFeedback = (event: FormEvent) => {
    event.preventDefault();
    generateJourney(Boolean(journey)).catch(showError);
  };

  return (
    <main className="app-shell">
      <section className="brief-column" aria-label="Briefing da playlist">
        <div className="brand-row">
          <div className="brand-mark">
            <Sparkles size={20} />
          </div>
          <div>
            <p>Smart DJ</p>
            <span>{config?.groq_enabled ? "Gemini + Spotify" : "Modo demonstração + Spotify"}</span>
          </div>
        </div>

        <header className="hero-copy">
          <p className="eyebrow">Playlist pelo papo</p>
          <h1>Descreva a vibe. O app monta e toca no Spotify.</h1>
        </header>

        <form className="brief-form" onSubmit={submitFeedback}>
          <label className="span-2">
            Situação
            <textarea
              rows={5}
              value={situation}
              onChange={(event) => setSituation(event.target.value)}
              placeholder="Ex: resenha em casa, começa tranquila e depois sobe para dançar."
            />
          </label>

          <label>
            Onde
            <select value={venue} onChange={(event) => setVenue(event.target.value as Venue)}>
              {Object.entries(venueLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Começar
            <select value={startEnergy} onChange={(event) => setStartEnergy(event.target.value as StartEnergy)}>
              {Object.entries(startLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Terminar
            <select value={endEnergy} onChange={(event) => setEndEnergy(event.target.value as EndEnergy)}>
              {Object.entries(endLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Seleção
            <select value={discovery} onChange={(event) => setDiscovery(event.target.value as Discovery)}>
              {Object.entries(discoveryLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label className="span-2">
            Duração: {duration} min
            <input
              type="range"
              min="30"
              max="120"
              step="15"
              value={duration}
              onChange={(event) => setDuration(Number(event.target.value))}
            />
          </label>

          <label className="span-2">
            Feedback / próxima mensagem
            <textarea
              rows={3}
              value={feedback}
              onChange={(event) => setFeedback(event.target.value)}
              placeholder="Ex: deixa mais atual, mais Brasil, menos pop internacional, pico mais forte."
            />
          </label>

          <div className="brief-actions span-2">
            <button type="button" className="primary-button" disabled={!canGenerate} onClick={() => generateJourney(false).catch(showError)}>
              {busy ? <Loader2 size={17} className="spin" /> : <Wand2 size={17} />}
              Gerar playlist
            </button>
            <button type="submit" disabled={!canGenerate || !journey}>
              <Send size={17} />
              Enviar feedback
            </button>
          </div>
        </form>

        <section className="chat-card" aria-label="Chat de curadoria">
          <div className="section-title">
            <MessageSquareText size={18} />
            <span>Conversa</span>
          </div>
          <div className="chat-thread">
            {chat.map((message) => (
              <article key={message.id} className={`chat-bubble ${message.role}`}>
                <strong>{message.role === "user" ? "Você" : "DJ Copilot"}</strong>
                <p>{message.text}</p>
              </article>
            ))}
            <div ref={chatEndRef} />
          </div>
        </section>
      </section>

      <section className="player-column" aria-label="Player e Spotify">
        <section className="player-card">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Player</p>
              <h2>{currentTrack?.name || "Spotify no app"}</h2>
              <span>{currentTrack ? `${currentTrack.artists} · faixa ${currentTrackIndex + 1} de ${tracks.length}` : "Ao gerar, a primeira música aparece aqui."}</span>
            </div>
            <Music2 size={24} />
          </div>

          {currentTrack ? (
            <iframe
              title="Spotify track player"
              src={trackEmbedUrl}
              loading="lazy"
              allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
            />
          ) : (
            <div className="player-placeholder">
              <Music2 size={38} />
              <strong>Fila local ainda não gerada</strong>
              <p>Clique em Gerar playlist. O app monta a fila local e carrega a primeira música no player.</p>
            </div>
          )}
        </section>

        <section className="spotify-card">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Saída</p>
              <h2>Fila local</h2>
              <span>
                {needsSpotifyReconnect
                  ? "Reconecte para buscar músicas no Spotify."
                  : spotifyToken
                    ? "Autenticado; pronto para buscar faixas."
                    : "Conecte para buscar faixas no Spotify."}
              </span>
            </div>
            <button type="button" onClick={() => connectSpotify().catch(showError)} disabled={!config?.spotify_client_id || busy}>
              {spotifyToken && !needsSpotifyReconnect ? <CheckCircle2 size={17} /> : <Sparkles size={17} />}
              {needsSpotifyReconnect ? "Reconectar" : spotifyToken ? "Conectado" : "Conectar"}
            </button>
          </div>

          <div className="output-actions">
            <button
              type="button"
              disabled={!canUseQueue || currentTrackIndex <= 0}
              onClick={() => setCurrentTrackIndex((index) => Math.max(0, index - 1))}
            >
              <SkipBack size={17} />
              Anterior
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={!canUseQueue || currentTrackIndex >= tracks.length - 1}
              onClick={() => setCurrentTrackIndex((index) => Math.min(tracks.length - 1, index + 1))}
            >
              <SkipForward size={17} />
              Próxima
            </button>
          </div>

          {status && (
            <div className="generation-status" aria-live="polite">
              <div className="status-line">
                <Loader2 size={16} className="spin" />
                <span>{status}</span>
              </div>
              <div className="progress-track">
                <i style={{ width: `${Math.max(progress, 8)}%` }} />
              </div>
            </div>
          )}

          <article className="playlist-summary-card">
            <div>
              <strong>{journey?.title || "Nenhuma fila local criada ainda"}</strong>
              <span>{tracks.length ? `${tracks.length} músicas · ${duration} min` : "Aguardando geração"}</span>
            </div>
            <p>
              {journey
                ? playlistMessage(false)
                : "A explicação da curadoria aparece aqui depois da geração. A fila fica local no app, e o player toca a música selecionada."}
            </p>
            {journey && (
              <div className="local-queue">
                {tracks.map((track, index) => (
                  <button
                    type="button"
                    key={`${track.spotifyId}-${index}`}
                    className={index === currentTrackIndex ? "is-active" : ""}
                    onClick={() => setCurrentTrackIndex(index)}
                  >
                    <span>{index + 1}</span>
                    <strong>{track.name}</strong>
                    <small>{track.artists}</small>
                    <em>
                      <b>{track.genre}</b>
                      <b>{energyTag(track.energy)}</b>
                      <b>{danceTag(track.danceability)}</b>
                      <b>{bpmTag(track.bpm)}</b>
                    </em>
                  </button>
                ))}
              </div>
            )}
          </article>
        </section>

        <ol className="event-log" aria-label="Eventos recentes">
          {events.length ? (
            events.map((event) => <li key={event.id}>{event.text}</li>)
          ) : (
            <li>Pronto para conectar, gerar e tocar faixa por faixa.</li>
          )}
        </ol>
      </section>
    </main>
  );
}
