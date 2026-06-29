const TOKEN_KEY = "dj-copilot-spotify-token";
const VERIFIER_KEY = "dj-copilot-pkce-verifier";
const AUTH_STATE_KEY = "dj-copilot-auth-state";

const state = {
  config: null,
  sessionId: null,
  stream: null,
  motionTimer: null,
  sampleTimer: null,
  countdownTimer: null,
  busy: false,
  visionBusy: false,
  visionFrames: [],
  motionScores: [],
  nextVisionAt: null,
  spotifyToken: null,
  playlistId: null,
  playlistName: null,
  catalog: [],
  selectedDeviceId: "",
  currentTrack: null,
  currentTrackStartedAt: 0,
  recentTrackIds: [],
  desiredHistory: [],
  desiredEnergy: 0.2,
  suggestion: null,
  researchingCatalog: false,
};

const $ = (selector) => document.querySelector(selector);
const video = $("#camera");
const canvas = $("#sample");
const visionCanvas = $("#visionSample");
const fallback = $("#cameraFallback");
const startButton = $("#startButton");
const analyzeNowButton = $("#analyzeNowButton");
const stopButton = $("#stopButton");
const energyLevel = $("#energyLevel");
const motionScore = $("#motionScore");
const visionConfidence = $("#visionConfidence");
const visionSummary = $("#visionSummary");
const visionDetails = $("#visionDetails");
const visionProvider = $("#visionProvider");
const visionCountdown = $("#visionCountdown");
const meterFill = $("#meterFill");
const trackTitle = $("#trackTitle");
const trackDetails = $("#trackDetails");
const trackCredit = $("#trackCredit");
const player = $("#player");
const events = $("#events");
const spotifyConnectButton = $("#spotifyConnectButton");
const spotifyStatus = $("#spotifyStatus");
const playlistInput = $("#playlistInput");
const playlistLoadButton = $("#playlistLoadButton");
const refreshDevicesButton = $("#refreshDevicesButton");
const deviceSelect = $("#deviceSelect");
const playlistName = $("#playlistName");
const catalogCount = $("#catalogCount");
const catalog = $("#catalog");
const researchCatalogButton = $("#researchCatalogButton");
const researchProgress = $("#researchProgress");
const researchProgressFill = $("#researchProgressFill");
const suggestionTitle = $("#suggestionTitle");
const suggestionReason = $("#suggestionReason");
const playSuggestionButton = $("#playSuggestionButton");
const autoDjToggle = $("#autoDjToggle");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = await response.text();
    try {
      detail = JSON.parse(detail).detail || detail;
    } catch {
      // Keep the response text.
    }
    throw new Error(detail || `Erro HTTP ${response.status}`);
  }
  return response.json();
}

async function ensureSession() {
  if (state.sessionId) return state.sessionId;
  const data = await api("/api/sessions", { method: "POST" });
  state.sessionId = data.session_id;
  return state.sessionId;
}

async function loadConfig() {
  state.config = await api("/api/config");
  visionProvider.textContent = state.config.groq_enabled ? "Groq Vision" : "visão local";
  spotifyConnectButton.disabled = !state.config.spotify_client_id;
  if (!state.config.spotify_client_id) {
    spotifyConnectButton.textContent = "Spotify não configurado";
    spotifyStatus.textContent = "SPOTIFY_CLIENT_ID não chegou ao servidor";
  }
}

async function startCamera() {
  await ensureSession();
  state.stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 960 }, height: { ideal: 540 }, facingMode: "environment" },
    audio: false,
  });
  video.srcObject = state.stream;
  video.classList.add("is-active");
  fallback.hidden = true;
  startButton.disabled = true;
  stopButton.disabled = false;
  analyzeNowButton.disabled = false;
  state.visionFrames = [];
  state.motionScores = [];
  state.nextVisionAt = Date.now() + state.config.vision_interval_seconds * 1000;
  captureVisionFrame();
  state.motionTimer = window.setInterval(captureAndAnalyzeMotion, 1000);
  state.sampleTimer = window.setInterval(captureVisionFrame, 12000);
  state.countdownTimer = window.setInterval(renderVisionCountdown, 1000);
  addEvent("Camera iniciada; coletando cinco amostras por minuto");
}

function stopCamera() {
  [state.motionTimer, state.sampleTimer, state.countdownTimer].forEach((timer) => {
    if (timer) window.clearInterval(timer);
  });
  state.motionTimer = null;
  state.sampleTimer = null;
  state.countdownTimer = null;
  if (state.stream) state.stream.getTracks().forEach((track) => track.stop());
  state.stream = null;
  video.srcObject = null;
  video.classList.remove("is-active");
  fallback.hidden = false;
  startButton.disabled = false;
  stopButton.disabled = true;
  analyzeNowButton.disabled = true;
  visionCountdown.textContent = "--";
  addEvent("Camera parada");
}

async function captureAndAnalyzeMotion() {
  if (state.busy || !video.videoWidth) return;
  state.busy = true;
  try {
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    const pixels = [];
    for (let index = 0; index < image.data.length; index += 4) {
      pixels.push(
        Math.round(
          image.data[index] * 0.299 +
            image.data[index + 1] * 0.587 +
            image.data[index + 2] * 0.114
        )
      );
    }
    const result = await api("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        session_id: await ensureSession(),
        width: canvas.width,
        height: canvas.height,
        pixels,
      }),
    });
    state.motionScores.push(result.motion_score);
    state.motionScores = state.motionScores.slice(-120);
    motionScore.textContent = result.motion_score.toFixed(2);
    meterFill.style.width = `${Math.min(100, result.motion_score * 3)}%`;
  } catch (error) {
    addEvent(error.message);
  } finally {
    state.busy = false;
  }
}

function captureVisionFrame() {
  if (!video.videoWidth) return;
  const context = visionCanvas.getContext("2d");
  context.drawImage(video, 0, 0, visionCanvas.width, visionCanvas.height);
  state.visionFrames.push(visionCanvas.toDataURL("image/jpeg", 0.58));
  state.visionFrames = state.visionFrames.slice(-5);
  if (state.nextVisionAt && Date.now() >= state.nextVisionAt) analyzeVision();
}

function renderVisionCountdown() {
  if (!state.nextVisionAt) return;
  const seconds = Math.max(0, Math.ceil((state.nextVisionAt - Date.now()) / 1000));
  visionCountdown.textContent = `${seconds}s`;
  if (seconds === 0) analyzeVision();
}

async function analyzeVision() {
  if (state.visionBusy || !state.visionFrames.length) return;
  state.visionBusy = true;
  state.nextVisionAt = Date.now() + state.config.vision_interval_seconds * 1000;
  analyzeNowButton.disabled = true;
  try {
    let result;
    if (state.config.groq_enabled) {
      result = await api("/api/vision/analyze", {
        method: "POST",
        body: JSON.stringify({
          frames: state.visionFrames,
          motion_scores: state.motionScores,
        }),
      });
    } else {
      const recent = state.motionScores.slice(-60);
      const average = recent.length ? recent.reduce((sum, value) => sum + value, 0) / recent.length : 0;
      const energy = Math.max(0, Math.min(1, average / 24));
      result = {
        energy,
        level: levelForEnergy(energy),
        confidence: recent.length >= 15 ? 0.45 : 0.2,
        people_count: null,
        active_ratio: null,
        summary: "Groq não configurado; usando apenas a tendência de diferença entre frames.",
        provider: "local",
      };
    }
    applyVisionResult(result);
  } catch (error) {
    addEvent(`Análise visual: ${error.message}`);
  } finally {
    state.visionBusy = false;
    analyzeNowButton.disabled = !state.stream;
  }
}

function applyVisionResult(result) {
  state.desiredEnergy = Number(result.energy);
  state.desiredHistory.push(result.level);
  state.desiredHistory = state.desiredHistory.slice(-3);
  energyLevel.textContent = result.level;
  energyLevel.className = `level-${result.level}`;
  visionConfidence.textContent = `${Math.round(result.confidence * 100)}%`;
  visionSummary.textContent = result.summary;
  const details = [];
  if (result.people_count !== null) details.push(`${result.people_count} pessoas visíveis`);
  if (result.active_ratio !== null) details.push(`${Math.round(result.active_ratio * 100)}% ativas`);
  visionDetails.textContent = details.length
    ? details.join(" · ")
    : "Atividade coletiva estimada; não mede satisfação.";
  chooseSuggestion();
  addEvent(`Leitura ${result.level}: ${result.summary}`);
  maybeAutoPlay();
}

function simulateEnergy(level) {
  const energyByLevel = { calma: 0.2, media: 0.52, alta: 0.84 };
  applyVisionResult({
    energy: energyByLevel[level],
    level,
    confidence: 0.99,
    people_count: null,
    active_ratio: energyByLevel[level],
    summary: `Simulação manual de pista com energia ${level}.`,
  });
}

function levelForEnergy(energy) {
  if (energy < 0.34) return "calma";
  if (energy < 0.67) return "media";
  return "alta";
}

function chooseSuggestion() {
  if (!state.catalog.length) return renderSuggestion(null);
  const recent = new Set(state.recentTrackIds.slice(-5));
  let candidates = state.catalog.filter(
    (track) => track.id !== state.currentTrack?.id && !recent.has(track.id)
  );
  if (!candidates.length) {
    candidates = state.catalog.filter((track) => track.id !== state.currentTrack?.id);
  }
  if (!candidates.length) candidates = [...state.catalog];
  candidates.sort((left, right) => matchScore(left) - matchScore(right));
  state.suggestion = candidates[0] || null;
  renderSuggestion(state.suggestion);
}

function matchScore(track) {
  const energyDistance = Math.abs(track.energy - state.desiredEnergy);
  const desiredDanceability = Math.max(0.25, Math.min(0.95, 0.3 + state.desiredEnergy * 0.7));
  const danceDistance = Math.abs(track.danceability - desiredDanceability);
  const bpmDistance =
    state.currentTrack?.bpm && track.bpm
      ? Math.min(1, Math.abs(track.bpm - state.currentTrack.bpm) / 24)
      : 0.25;
  const uncertainty = 1 - track.confidence;
  return energyDistance * 0.58 + danceDistance * 0.2 + bpmDistance * 0.14 + uncertainty * 0.08;
}

function renderSuggestion(track) {
  state.suggestion = track;
  playSuggestionButton.disabled = !track || !state.spotifyToken;
  if (!track) {
    suggestionTitle.textContent = "Importe e classifique uma playlist";
    suggestionReason.textContent = "O seletor procura energia próxima da leitura e evita repetições.";
    return;
  }
  suggestionTitle.textContent = `${track.name} — ${track.artists}`;
  suggestionReason.textContent =
    `${track.genre} · energia ${Math.round(track.energy * 100)}% · ` +
    `${track.bpm ? `${track.bpm} BPM · ` : ""}match com alvo ${Math.round(state.desiredEnergy * 100)}%`;
}

async function maybeAutoPlay() {
  if (!autoDjToggle.checked || !state.suggestion || !state.selectedDeviceId) return;
  const coherent =
    state.desiredHistory.length >= 2 &&
    state.desiredHistory.at(-1) === state.desiredHistory.at(-2);
  const elapsed = (Date.now() - state.currentTrackStartedAt) / 1000;
  const canChange = !state.currentTrack || elapsed >= state.config.min_track_seconds;
  if (coherent && canChange) {
    await playTrack(state.suggestion).catch((error) => addEvent(error.message));
  } else if (!canChange) {
    const left = Math.ceil(state.config.min_track_seconds - elapsed);
    addEvent(`Sugestão pronta; aguardando ${left}s de tempo mínimo da faixa`);
  }
}

async function playTrack(track) {
  if (!state.selectedDeviceId) throw new Error("Selecione um dispositivo Spotify");
  await spotifyFetch(`/me/player/play?device_id=${encodeURIComponent(state.selectedDeviceId)}`, {
    method: "PUT",
    body: JSON.stringify({ uris: [track.uri], position_ms: 0 }),
  });
  if (state.currentTrack) state.recentTrackIds.push(state.currentTrack.id);
  state.recentTrackIds = state.recentTrackIds.slice(-10);
  state.currentTrack = track;
  state.currentTrackStartedAt = Date.now();
  trackTitle.textContent = track.name;
  trackDetails.textContent =
    `${track.artists} · ${track.genre} · energia ${Math.round(track.energy * 100)}%` +
    (track.bpm ? ` · ${track.bpm} BPM` : "");
  trackCredit.href = track.externalUrl;
  trackCredit.textContent = "Abrir faixa no Spotify";
  player.hidden = true;
  addEvent(`Spotify tocando: ${track.name}`);
  chooseSuggestion();
}

function parsePlaylistId(value) {
  const trimmed = value.trim();
  const uriMatch = trimmed.match(/^spotify:playlist:([A-Za-z0-9]+)$/);
  if (uriMatch) return uriMatch[1];
  try {
    const url = new URL(trimmed);
    const match = url.pathname.match(/\/playlist\/([A-Za-z0-9]+)/);
    if (match) return match[1];
  } catch {
    // Accept a raw playlist ID below.
  }
  return /^[A-Za-z0-9]+$/.test(trimmed) ? trimmed : null;
}

async function importPlaylist() {
  if (!state.spotifyToken) {
    throw new Error("Spotify ainda não autenticado. Clique em Conectar Spotify.");
  }
  const id = parsePlaylistId(playlistInput.value);
  if (!id) throw new Error("URL ou ID de playlist inválido");
  playlistLoadButton.disabled = true;
  try {
    const metadata = await spotifyFetch(
      `/playlists/${id}?fields=id,name,external_urls,tracks(total)`
    );
    let items = [];
    let offset = 0;
    let useLegacyPath = false;
    while (true) {
      const path = useLegacyPath
        ? `/playlists/${id}/tracks?limit=50&offset=${offset}`
        : `/playlists/${id}/items?limit=50&offset=${offset}`;
      let page;
      try {
        page = await spotifyFetch(path);
      } catch (error) {
        if (!useLegacyPath && error.status === 404) {
          useLegacyPath = true;
          continue;
        }
        throw error;
      }
      items.push(...page.items);
      offset += page.items.length;
      if (!page.next || !page.items.length) break;
    }
    state.playlistId = id;
    state.playlistName = metadata.name;
    state.catalog = items
      .map((entry) => entry.item || entry.track)
      .filter((track) => track?.id && track?.uri && track.type === "track")
      .map((track) => ({
        id: track.id,
        uri: track.uri,
        name: track.name,
        artists: (track.artists || []).map((artist) => artist.name).join(", "),
        durationMs: track.duration_ms,
        externalUrl: track.external_urls?.spotify || `https://open.spotify.com/track/${track.id}`,
        imageUrl: track.album?.images?.at(-1)?.url || "",
        ...loadStoredProfile(track.id),
      }));
    renderCatalog();
    chooseSuggestion();
    addEvent(`Playlist importada: ${metadata.name} (${state.catalog.length} faixas)`);
    researchCatalogButton.disabled = !state.config.groq_enabled || !state.catalog.length;
    const pending = state.catalog.filter((track) => !track.researched).length;
    if (pending && state.config.groq_enabled) {
      await researchCatalog();
    }
  } finally {
    playlistLoadButton.disabled = false;
  }
}

function profileStorageKey(trackId) {
  return `dj-copilot-profile:${trackId}`;
}

function loadStoredProfile(trackId) {
  const stored = localStorage.getItem(profileStorageKey(trackId));
  if (!stored) {
    return {
      energy: 0.5,
      danceability: 0.5,
      bpm: null,
      genre: "aguardando pesquisa",
      confidence: 0,
      reason: "Ainda não pesquisada pelo Groq.",
      researched: false,
    };
  }
  try {
    return { ...JSON.parse(stored), researched: true };
  } catch {
    localStorage.removeItem(profileStorageKey(trackId));
    return loadStoredProfile(trackId);
  }
}

function saveTrackProfile(track) {
  localStorage.setItem(
    profileStorageKey(track.id),
    JSON.stringify({
      energy: track.energy,
      danceability: track.danceability,
      bpm: track.bpm,
      genre: track.genre,
      confidence: track.confidence,
      reason: track.reason,
    })
  );
}

async function researchCatalog(force = false) {
  if (state.researchingCatalog) return;
  if (!state.config.groq_enabled) throw new Error("Configure GROQ_API_KEY para pesquisar músicas");
  const targets = force ? [...state.catalog] : state.catalog.filter((track) => !track.researched);
  if (!targets.length) {
    addEvent("Todas as músicas já possuem pesquisa salva");
    return;
  }
  state.researchingCatalog = true;
  researchCatalogButton.disabled = true;
  playlistLoadButton.disabled = true;
  researchProgress.hidden = false;
  let completed = 0;
  let failed = 0;
  try {
    for (let index = 0; index < targets.length; index += 2) {
      const batch = targets.slice(index, index + 2);
      try {
        const result = await api("/api/music/research", {
          method: "POST",
          body: JSON.stringify({
            tracks: batch.map((track) => ({
              id: track.id,
              title: track.name,
              artist: track.artists,
            })),
          }),
        });
        const profiles = new Map(result.tracks.map((profile) => [profile.id, profile]));
        batch.forEach((track) => {
          const profile = profiles.get(track.id);
          if (!profile) {
            failed += 1;
            return;
          }
          Object.assign(track, profile, { researched: true });
          saveTrackProfile(track);
          completed += 1;
        });
      } catch (error) {
        failed += batch.length;
        addEvent(`Pesquisa do lote falhou: ${error.message}`);
      }
      const processed = Math.min(index + batch.length, targets.length);
      researchProgressFill.style.width = `${Math.round((processed / targets.length) * 100)}%`;
      catalogCount.textContent = `${completed}/${targets.length} pesquisadas`;
      renderCatalog();
      chooseSuggestion();
    }
    addEvent(
      `Pesquisa concluída: ${completed} músicas classificadas` +
        (failed ? `, ${failed} sem resultado` : "")
    );
  } finally {
    state.researchingCatalog = false;
    researchCatalogButton.disabled = false;
    playlistLoadButton.disabled = false;
    window.setTimeout(() => {
      researchProgress.hidden = true;
      researchProgressFill.style.width = "0%";
    }, 1200);
    renderCatalog();
    chooseSuggestion();
  }
}

function renderCatalog() {
  playlistName.textContent = state.playlistName || "Playlist";
  catalogCount.textContent = `${state.catalog.length} faixas`;
  catalog.replaceChildren();
  state.catalog.forEach((track) => {
    const row = document.createElement("article");
    row.className = "catalog-row";

    const identity = document.createElement("div");
    identity.className = "track-identity";
    const title = document.createElement("strong");
    title.textContent = track.name;
    const artist = document.createElement("span");
    artist.textContent = track.artists;
    const metadata = document.createElement("small");
    metadata.textContent = track.researched
      ? `${track.genre} · ${track.bpm ? `${track.bpm} BPM · ` : ""}${Math.round(track.confidence * 100)}% confiança`
      : "Aguardando pesquisa Groq";
    metadata.title = track.reason;
    identity.append(title, artist, metadata);

    const control = document.createElement("label");
    control.className = "energy-control";
    const value = document.createElement("output");
    value.textContent = `${Math.round(track.energy * 100)}%`;
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = "0";
    slider.max = "100";
    slider.value = String(Math.round(track.energy * 100));
    slider.setAttribute("aria-label", `Energia de ${track.name}`);
    slider.addEventListener("input", () => {
      track.energy = Number(slider.value) / 100;
      track.researched = true;
      track.reason = "Energia corrigida manualmente.";
      value.textContent = `${slider.value}%`;
      saveTrackProfile(track);
      chooseSuggestion();
    });
    control.append(value, slider);

    const play = document.createElement("button");
    play.type = "button";
    play.textContent = "Tocar";
    play.addEventListener("click", () => playTrack(track).catch((error) => addEvent(error.message)));
    row.append(identity, control, play);
    catalog.append(row);
  });
  if (!state.researchingCatalog) {
    catalogCount.textContent = `${state.catalog.length} faixas`;
  }
}

async function refreshDevices() {
  const data = await spotifyFetch("/me/player/devices");
  deviceSelect.replaceChildren();
  if (!data.devices.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Abra o Spotify em algum dispositivo";
    deviceSelect.append(option);
    state.selectedDeviceId = "";
  } else {
    data.devices.forEach((device) => {
      const option = document.createElement("option");
      option.value = device.id;
      option.textContent = `${device.name} · ${device.type}${device.is_active ? " · ativo" : ""}`;
      option.selected = device.is_active;
      deviceSelect.append(option);
    });
    state.selectedDeviceId =
      data.devices.find((device) => device.is_active)?.id || data.devices[0].id;
    deviceSelect.value = state.selectedDeviceId;
  }
}

function randomString(length = 64) {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes, (byte) => "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"[byte % 62]).join("");
}

function base64Url(buffer) {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

async function connectSpotify() {
  if (!state.config.spotify_client_id) throw new Error("Defina SPOTIFY_CLIENT_ID no backend");
  const verifier = randomString();
  const challenge = base64Url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const authState = randomString(24);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(AUTH_STATE_KEY, authState);
  const params = new URLSearchParams({
    client_id: state.config.spotify_client_id,
    response_type: "code",
    redirect_uri: spotifyRedirectUri(),
    scope: [
      "playlist-read-private",
      "playlist-read-collaborative",
      "user-read-playback-state",
      "user-modify-playback-state",
    ].join(" "),
    code_challenge_method: "S256",
    code_challenge: challenge,
    state: authState,
  });
  window.location.assign(`https://accounts.spotify.com/authorize?${params}`);
}

function spotifyRedirectUri() {
  return `${window.location.origin}${window.location.pathname}`;
}

async function handleSpotifyCallback() {
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
  const response = await fetch("https://accounts.spotify.com/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: state.config.spotify_client_id,
      grant_type: "authorization_code",
      code,
      redirect_uri: spotifyRedirectUri(),
      code_verifier: verifier,
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Não foi possível concluir o login do Spotify: ${detail}`);
  }
  saveSpotifyToken(await response.json());
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(AUTH_STATE_KEY);
  history.replaceState({}, document.title, window.location.pathname);
}

function saveSpotifyToken(token) {
  state.spotifyToken = {
    ...token,
    expires_at: Date.now() + token.expires_in * 1000,
    refresh_token: token.refresh_token || state.spotifyToken?.refresh_token,
  };
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify(state.spotifyToken));
}

async function refreshSpotifyToken() {
  if (!state.spotifyToken?.refresh_token) throw new Error("Reconecte o Spotify");
  const response = await fetch("https://accounts.spotify.com/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: state.config.spotify_client_id,
      grant_type: "refresh_token",
      refresh_token: state.spotifyToken.refresh_token,
    }),
  });
  if (!response.ok) throw new Error("A sessão do Spotify expirou");
  saveSpotifyToken(await response.json());
}

async function spotifyFetch(path, options = {}, retry = true) {
  if (!state.spotifyToken) throw new Error("Conecte o Spotify primeiro");
  if (Date.now() >= state.spotifyToken.expires_at - 30000) await refreshSpotifyToken();
  const response = await fetch(`https://api.spotify.com/v1${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${state.spotifyToken.access_token}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (response.status === 401 && retry) {
    await refreshSpotifyToken();
    return spotifyFetch(path, options, false);
  }
  if (!response.ok) {
    const error = new Error((await response.text()) || `Spotify HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

async function restoreSpotify() {
  const stored = sessionStorage.getItem(TOKEN_KEY);
  if (stored) {
    try {
      state.spotifyToken = JSON.parse(stored);
    } catch {
      sessionStorage.removeItem(TOKEN_KEY);
    }
  }
  await handleSpotifyCallback();
  if (!state.spotifyToken) {
    spotifyStatus.textContent = "Não conectado";
    playlistLoadButton.disabled = false;
    return;
  }
  spotifyConnectButton.textContent = "Spotify conectado";
  spotifyStatus.textContent = "Autenticado; agora cole uma playlist";
  playlistLoadButton.disabled = false;
  refreshDevicesButton.disabled = false;
  deviceSelect.disabled = false;
  await refreshDevices().catch((error) => addEvent(error.message));
}

function addEvent(message) {
  const item = document.createElement("li");
  item.textContent = `${new Date().toLocaleTimeString("pt-BR")} · ${message}`;
  events.prepend(item);
  while (events.children.length > 8) events.lastChild.remove();
}

startButton.addEventListener("click", () => startCamera().catch((error) => addEvent(error.message)));
stopButton.addEventListener("click", stopCamera);
analyzeNowButton.addEventListener("click", () => {
  captureVisionFrame();
  analyzeVision();
});
spotifyConnectButton.addEventListener("click", () =>
  connectSpotify().catch((error) => addEvent(error.message))
);
playlistLoadButton.addEventListener("click", () =>
  importPlaylist().catch((error) => addEvent(error.message))
);
researchCatalogButton.addEventListener("click", () =>
  researchCatalog(true).catch((error) => addEvent(error.message))
);
refreshDevicesButton.addEventListener("click", () =>
  refreshDevices().catch((error) => addEvent(error.message))
);
deviceSelect.addEventListener("change", () => {
  state.selectedDeviceId = deviceSelect.value;
});
playSuggestionButton.addEventListener("click", () => {
  if (state.suggestion) playTrack(state.suggestion).catch((error) => addEvent(error.message));
});
document.querySelectorAll("[data-level]").forEach((button) => {
  button.addEventListener("click", () => simulateEnergy(button.dataset.level));
});

async function init() {
  await Promise.all([loadConfig(), ensureSession()]);
  try {
    await restoreSpotify();
  } catch (error) {
    spotifyStatus.textContent = "Falha na autenticação";
    playlistLoadButton.disabled = false;
    addEvent(error.message);
  }
  addEvent(
    state.config.groq_enabled
      ? "Sessão pronta; Groq Vision configurado"
      : "Sessão pronta; adicione GROQ_API_KEY para ativar visão multimodal"
  );
}

init().catch((error) => addEvent(error.message));
