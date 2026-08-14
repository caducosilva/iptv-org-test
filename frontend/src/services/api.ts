import {
  HealthResponse,
  DevicesResponse,
  ScanResponse,
  PlaylistsResponse,
  CatalogResponse,
  ChannelsResponse,
  PreviewResponse,
  ProbeStatusResponse,
  CastResponse,
  CastStatusResponse,
  CastRequestBody,
  Channel,
} from '../types';

let baseUrl = 'http://127.0.0.1:8769';

// Modo simulação NUNCA liga sozinho.
// Antes, qualquer request lento (ex.: /scan leva ~11s) caía no mock e o app
// passava a "fingir" que transmitia: o botão dizia SUCESSO e a TV não recebia nada.
let isMockMode = false;

export function getBaseUrl(): string {
  return baseUrl;
}

export function setBaseUrl(url: string) {
  baseUrl = url.replace(/\/+$/, '');
}

export function getIsMockMode(): boolean {
  return isMockMode;
}

export function setMockMode(enabled: boolean) {
  isMockMode = enabled;
}

/**
 * Timeout por operação (ms). Cada endpoint tem um custo real diferente:
 * o scan de rede leva ~11s e o cast espera a TV responder.
 */
const TIMEOUTS: { test: RegExp; ms: number }[] = [
  { test: /^\/scan/, ms: 40000 },
  { test: /^\/channels/, ms: 25000 },
  { test: /^\/catalog\/reload/, ms: 30000 },
  { test: /^\/preview/, ms: 20000 },
  { test: /^\/probe\/batch/, ms: 15000 },
  { test: /^\/cast/, ms: 15000 },
  { test: /^\/playlists/, ms: 10000 },
];
const DEFAULT_TIMEOUT = 8000;

function timeoutFor(path: string): number {
  return TIMEOUTS.find((t) => t.test.test(path))?.ms ?? DEFAULT_TIMEOUT;
}

export class ApiError extends Error {
  status: number;
  isTimeout: boolean;
  isOffline: boolean;

  constructor(message: string, opts: { status?: number; isTimeout?: boolean; isOffline?: boolean } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status ?? 0;
    this.isTimeout = Boolean(opts.isTimeout);
    this.isOffline = Boolean(opts.isOffline);
  }
}

// Notificação de conectividade para a UI (banner do topo)
type ConnectionListener = (online: boolean, error?: string) => void;
let connectionListener: ConnectionListener | null = null;

export function onConnectionChange(fn: ConnectionListener | null) {
  connectionListener = fn;
}

let lastOnline: boolean | null = null;

function reportConnection(online: boolean, error?: string) {
  if (lastOnline !== online) {
    lastOnline = online;
    connectionListener?.(online, error);
  }
}

// Helper fetch wrapper
async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  if (isMockMode) {
    return getMockResponse<T>(path, options);
  }

  const fullUrl = `${baseUrl}${path}`;
  const controller = new AbortController();
  const ms = timeoutFor(path);
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, ms);

  try {
    const res = await fetch(fullUrl, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(options?.headers || {}),
      },
    });

    clearTimeout(timeoutId);
    reportConnection(true);

    if (!res.ok && res.status !== 409) {
      const text = await res.text().catch(() => '');
      let detail = text || res.statusText;
      try {
        const parsed = JSON.parse(text);
        detail = parsed.message || parsed.error || detail;
      } catch {
        // texto puro mesmo
      }
      throw new ApiError(detail, { status: res.status });
    }

    return await res.json();
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err instanceof ApiError) throw err;

    if (timedOut) {
      const msg = `A operação demorou mais que ${Math.round(ms / 1000)}s e foi cancelada (${path}).`;
      console.warn('[IPTV Companion]', msg);
      throw new ApiError(msg, { isTimeout: true });
    }

    // Backend realmente fora do ar / bloqueado
    const msg = `Sem conexão com o servidor local em ${baseUrl} (${path}).`;
    console.warn('[IPTV Companion]', msg, err);
    reportConnection(false, msg);
    throw new ApiError(msg, { isOffline: true });
  }
}

// API methods matching the exact spec
export const api = {
  getHealth: () => fetchApi<HealthResponse>('/health'),
  
  getDevices: () => fetchApi<DevicesResponse>('/devices'),
  
  scanDevices: () => fetchApi<ScanResponse>('/scan'),
  
  getPlaylists: () => fetchApi<PlaylistsResponse>('/playlists'),
  
  getCatalog: () => fetchApi<CatalogResponse>('/catalog'),
  
  reloadCatalog: () => fetchApi<CatalogResponse>('/catalog/reload'),
  
  getChannels: (params: {
    q?: string;
    playlist?: string;
    limit?: number;
    hide_dead?: boolean;
  }) => {
    const query = new URLSearchParams();
    if (params.q) query.set('q', params.q);
    if (params.playlist && params.playlist !== 'TODAS') query.set('playlist', params.playlist);
    if (params.limit) query.set('limit', String(params.limit));
    if (params.hide_dead) query.set('hide_dead', '1');

    const qs = query.toString();
    return fetchApi<ChannelsResponse>(`/channels${qs ? `?${qs}` : ''}`);
  },

  getPreview: (url: string, name: string) => {
    const params = new URLSearchParams({
      url,
      name,
    });
    return fetchApi<PreviewResponse>(`/preview?${params.toString()}`);
  },

  getProbeStatus: () => fetchApi<ProbeStatusResponse>('/probe/status'),

  batchProbe: (channels: { url: string; name: string }[], workers = 6) => {
    return fetchApi<{ ok: boolean; started: boolean; queued: number }>('/probe/batch', {
      method: 'POST',
      body: JSON.stringify({ channels, workers }),
    });
  },

  cast: (body: CastRequestBody) => {
    return fetchApi<CastResponse>('/cast', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  stopCast: (reason = 'cancelado pelo usuario') => {
    return fetchApi<{ ok: boolean; stopped: boolean }>('/cast/stop', {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  getCastStatus: () => fetchApi<CastStatusResponse>('/cast_status'),

  getCastLog: () => fetchApi<{ logs: string[] }>('/cast_log'),

  getIsMockMode: () => getIsMockMode(),

  setMockMode: (enabled: boolean) => setMockMode(enabled),
};

// Mock data generator for offline/preview demonstration mode
let mockVersion = 3;
let mockProbeDone = 0;
let mockProbeTotal = 0;
let mockProbeRunning = false;
let mockCastPending = false;
let mockCastStep = 0;

const mockPlaylists = [
  { name: 'canais_abertos', file: 'canais_abertos.m3u', count: 18, mtime: 1718000000 },
  { name: 'esportes_hd', file: 'esportes_hd.m3u', count: 42, mtime: 1718001000 },
  { name: 'filmes_series', file: 'filmes_series.m3u', count: 120, mtime: 1718002000 },
  { name: 'noticias_variedades', file: 'noticias_variedades.m3u', count: 35, mtime: 1718003000 },
];

const mockChannelsData: Channel[] = [
  {
    name: 'TV Globo Rio de Janeiro (720p)',
    url: 'http://45.190.28.50/GLOBO_HD/index.m3u8',
    playlist: 'canais_abertos',
    group: 'VARIEDADES',
    score: 98,
    signalStrength: 98,
    codecs: ['H.264', 'AAC'],
    bitrate: '3.8 Mbps',
    health: 'confirmed',
    confirmed: true,
  },
  {
    name: 'TV Globo São Paulo (Sinal Fraco 1080p)',
    url: 'http://45.190.28.51/GLOBO_SP/index.m3u8',
    playlist: 'canais_abertos',
    group: 'VARIEDADES',
    score: 15,
    signalStrength: 15,
    codecs: ['H.264', 'MP3'],
    bitrate: '1.1 Mbps',
    health: 'doubt',
    health_error: 'Sinal Instavel / Perda de Pacotes (15%)',
    confirmed: false,
  },
  {
    name: 'TV Globo Minas Gerais (HD Alt)',
    url: 'http://45.190.28.52/GLOBO_MG/index.m3u8',
    playlist: 'canais_abertos',
    group: 'VARIEDADES',
    score: 88,
    signalStrength: 88,
    codecs: ['HEVC', 'AAC'],
    bitrate: '4.5 Mbps',
    health: 'ok',
    confirmed: false,
  },
  {
    name: 'SBT HD',
    url: 'http://stream.sbt.com.br/hls/sbt/index.m3u8',
    playlist: 'canais_abertos',
    group: 'VARIEDADES',
    score: 90,
    signalStrength: 90,
    codecs: ['H.264', 'AAC'],
    bitrate: '3.2 Mbps',
    health: 'ok',
    confirmed: false,
  },
  {
    name: 'Record TV HD',
    url: 'http://stream.record.com.br/hls/record/index.m3u8',
    playlist: 'canais_abertos',
    group: 'VARIEDADES',
    score: 85,
    signalStrength: 85,
    codecs: ['H.264', 'AAC'],
    bitrate: '2.9 Mbps',
    health: 'ok',
    confirmed: false,
  },
  {
    name: 'SporTV 1 1080p',
    url: 'http://iptv.example.com/sportv1/index.m3u8',
    playlist: 'esportes_hd',
    group: 'ESPORTES',
    score: 92,
    signalStrength: 92,
    codecs: ['H.264', 'AAC'],
    bitrate: '4.2 Mbps',
    health: 'confirmed',
    confirmed: true,
  },
  {
    name: 'SporTV 2 HD (Sinal Fraco)',
    url: 'http://iptv.example.com/sportv2/index.m3u8',
    playlist: 'esportes_hd',
    group: 'ESPORTES',
    score: 22,
    signalStrength: 22,
    codecs: ['MPEG-2'],
    bitrate: '1.5 Mbps',
    health: 'doubt',
    health_fail: 1,
    health_error: 'Timeout 4000ms / Oscilação',
    confirmed: false,
  },
  {
    name: 'ESPN Brasil HD',
    url: 'http://iptv.example.com/espnbr/index.m3u8',
    playlist: 'esportes_hd',
    group: 'ESPORTES',
    score: 88,
    signalStrength: 88,
    codecs: ['H.264', 'AAC'],
    bitrate: '3.5 Mbps',
    health: 'ok',
    confirmed: false,
  },
  {
    name: 'CazéTV Ao Vivo',
    url: 'http://iptv.example.com/cazetv/index.m3u8',
    playlist: 'esportes_hd',
    group: 'ESPORTES',
    score: 95,
    signalStrength: 95,
    codecs: ['AV1', 'AAC'],
    bitrate: '5.0 Mbps',
    health: 'ok',
    confirmed: false,
  },
  {
    name: 'Premiere Clubes 1',
    url: 'http://iptv.example.com/pfc1/index.m3u8',
    playlist: 'esportes_hd',
    group: 'FUTEBOL',
    score: 0,
    signalStrength: 0,
    codecs: ['Desconhecido'],
    bitrate: '0 Kbps',
    health: 'dead',
    health_fail: 3,
    health_error: 'HTTP 404 Not Found',
    confirmed: false,
  },
  {
    name: 'HBO Signature HD',
    url: 'http://iptv.example.com/hbo_sig/index.m3u8',
    playlist: 'filmes_series',
    group: 'CINEMA',
    score: 0,
    signalStrength: 0,
    health: 'unknown',
    confirmed: false,
  },
  {
    name: 'Telecine Action HD',
    url: 'http://iptv.example.com/tc_action/index.m3u8',
    playlist: 'filmes_series',
    group: 'CINEMA',
    score: 80,
    signalStrength: 80,
    codecs: ['H.264', 'AC3'],
    bitrate: '3.0 Mbps',
    health: 'ok',
    confirmed: false,
  },
  {
    name: 'BandNews TV HD',
    url: 'http://iptv.example.com/bandnews/index.m3u8',
    playlist: 'noticias_variedades',
    group: 'NOTICIAS',
    score: 82,
    signalStrength: 82,
    codecs: ['H.264', 'AAC'],
    bitrate: '2.8 Mbps',
    health: 'ok',
    confirmed: false,
  },
  {
    name: 'GloboNews HD',
    url: 'http://iptv.example.com/globonews/index.m3u8',
    playlist: 'noticias_variedades',
    group: 'NOTICIAS',
    score: 91,
    signalStrength: 91,
    codecs: ['H.264', 'AAC'],
    bitrate: '3.6 Mbps',
    health: 'confirmed',
    confirmed: true,
  },
];

async function getMockResponse<T>(path: string, options?: RequestInit): Promise<T> {
  await new Promise((r) => setTimeout(r, 150)); // simulate latency

  if (path === '/health') {
    return {
      ok: true,
      ip: '192.168.0.25 (Modo Simulação)',
      devices: 1,
      cast: {
        phase: mockCastPending ? 'started' : 'idle',
        ok: true,
        message: mockCastPending ? 'Iniciando transmissao' : 'Pronto',
        device: '50PUG7907/78 @ 192.168.0.27',
        url: 'http://45.190.28.50/GLOBO_HD/index.m3u8',
        title: 'TV Globo Rio de Janeiro (720p)',
        updatedAt: new Date().toISOString(),
      },
      pending: mockCastPending,
    } as unknown as T;
  }

  if (path === '/devices' || path === '/scan') {
    if (path === '/scan') {
      await new Promise((r) => setTimeout(r, 1200)); // scan duration
    }
    return {
      count: 2,
      devices: [
        {
          friendlyName: '50PUG7907/78 (Philips TV)',
          host: '192.168.0.27',
          type: 'chromecast',
          manufacturer: 'TP Vision',
        },
        {
          friendlyName: 'Chromecast Sala',
          host: '192.168.0.18',
          type: 'chromecast',
          manufacturer: 'Google',
        },
      ],
    } as unknown as T;
  }

  if (path === '/playlists') {
    return {
      playlists: mockPlaylists,
      version: mockVersion,
      folder: 'D:\\IPTV',
    } as unknown as T;
  }

  if (path === '/catalog' || path === '/catalog/reload') {
    if (path === '/catalog/reload') {
      mockVersion++;
    }
    return {
      changed: path === '/catalog/reload',
      version: mockVersion,
      folder: 'D:\\IPTV',
      playlists: mockPlaylists.length,
      channels: mockChannelsData.length,
    } as unknown as T;
  }

  if (path.startsWith('/channels')) {
    const urlObj = new URL(`http://dummy${path}`);
    const q = (urlObj.searchParams.get('q') || '').toLowerCase();
    const playlist = urlObj.searchParams.get('playlist') || '';
    const hideDead = urlObj.searchParams.get('hide_dead') === '1';

    let filtered = mockChannelsData.filter((c) => {
      if (q && !c.name.toLowerCase().includes(q) && !(c.group || '').toLowerCase().includes(q)) {
        return false;
      }
      if (playlist && playlist !== 'TODAS' && c.playlist !== playlist) {
        return false;
      }
      if (hideDead && c.health === 'dead' && !c.confirmed) {
        return false;
      }
      return true;
    });

    const counts = {
      ok: mockChannelsData.filter((c) => c.health === 'ok').length,
      doubt: mockChannelsData.filter((c) => c.health === 'doubt').length,
      dead: mockChannelsData.filter((c) => c.health === 'dead').length,
      confirmed: mockChannelsData.filter((c) => c.health === 'confirmed' || c.confirmed).length,
      unknown: mockChannelsData.filter((c) => c.health === 'unknown').length,
    };

    return {
      query: q,
      playlist,
      count: filtered.length,
      channels: filtered,
      version: mockVersion,
      folder: 'D:\\IPTV',
      hide_dead: hideDead,
      health: { counts },
    } as unknown as T;
  }

  if (path.startsWith('/preview')) {
    const urlObj = new URL(`http://dummy${path}`);
    const channelUrl = urlObj.searchParams.get('url') || '';
    const name = urlObj.searchParams.get('name') || '';

    const ch = mockChannelsData.find((c) => c.url === channelUrl || c.name === name);

    if (ch && ch.health === 'dead') {
      return {
        ok: false,
        url: channelUrl,
        fail_class: 'hard',
        health: 'dead',
        error: ch.health_error || 'HTTP 404 Not Found - Canal Offline',
      } as unknown as T;
    }

    return {
      ok: true,
      url: channelUrl,
      contentType: 'application/vnd.apple.mpegurl',
      bytes: 184320,
      hls: true,
      fail_class: 'ok',
      health: ch?.confirmed ? 'confirmed' : 'ok',
    } as unknown as T;
  }

  if (path === '/probe/status') {
    if (mockProbeRunning) {
      mockProbeDone += 2;
      if (mockProbeDone >= mockProbeTotal) {
        mockProbeDone = mockProbeTotal;
        mockProbeRunning = false;
      }
    }

    const counts = {
      ok: mockChannelsData.filter((c) => c.health === 'ok').length,
      doubt: mockChannelsData.filter((c) => c.health === 'doubt').length,
      dead: mockChannelsData.filter((c) => c.health === 'dead').length,
      confirmed: mockChannelsData.filter((c) => c.health === 'confirmed' || c.confirmed).length,
      unknown: mockChannelsData.filter((c) => c.health === 'unknown').length,
    };

    return {
      stats: { counts },
      probe: {
        running: mockProbeRunning,
        paused: false,
        done: mockProbeDone,
        total: mockProbeTotal,
        ok: counts.ok,
        doubt: counts.doubt,
        dead: counts.dead,
        errors: 1,
        last_url: mockChannelsData[0]?.url || '',
        last_message: mockProbeRunning ? 'Verificando stream HTTP...' : 'Concluido',
        started_at: new Date().toISOString(),
      },
    } as unknown as T;
  }

  if (path === '/probe/batch') {
    mockProbeRunning = true;
    mockProbeDone = 0;
    mockProbeTotal = 12;
    return { ok: true, started: true, queued: 12 } as unknown as T;
  }

  if (path === '/cast') {
    mockCastPending = true;
    mockCastStep = 0;
    const body = options?.body ? JSON.parse(options.body as string) : {};
    return {
      ok: true,
      started: true,
      pending: true,
      device: body.deviceLabel || body.deviceName,
      url: body.url,
      title: body.title,
      message: 'Comando de espelhamento enviado para TV',
    } as unknown as T;
  }

  if (path === '/cast/stop' || path === '/cast/cancel') {
    const wasPending = mockCastPending;
    mockCastPending = false;
    mockCastStep = 0;
    return { ok: true, stopped: wasPending } as unknown as T;
  }

  if (path === '/cast_status') {
    if (mockCastPending) {
      mockCastStep++;
      if (mockCastStep >= 3) {
        mockCastPending = false;
        return {
          pending: false,
          ok: true,
          phase: 'success',
          message: 'SUCCESS player=PLAYING (Fluxo de mídia iniciado com sucesso)',
          error: null,
          device: '50PUG7907/78',
          host: '192.168.0.27',
          url: 'http://45.190.28.50/GLOBO_HD/index.m3u8',
          source_url: 'http://45.190.28.50/GLOBO_HD/index.m3u8',
          title: 'TV Globo Rio de Janeiro (720p)',
          player: 'PLAYING',
          content_id: 'media_98231',
          app: 'Default Media Receiver',
          logs: ['[INFO] Conectado ao Chromecast', '[INFO] Carregando midia HLS', '[SUCCESS] Player rodando em PLAYING'],
        } as unknown as T;
      }
      return {
        pending: true,
        ok: true,
        phase: 'running',
        message: 'Carregando buffer no Chromecast...',
        error: null,
        device: '50PUG7907/78',
        host: '192.168.0.27',
        url: '',
        source_url: '',
        title: '',
        player: 'BUFFERING',
      } as unknown as T;
    }

    return {
      pending: false,
      ok: true,
      phase: 'idle',
      message: 'Sem transmissao ativa no momento',
      error: null,
      device: null,
      host: null,
      url: null,
      source_url: null,
      title: null,
      player: 'IDLE',
    } as unknown as T;
  }

  if (path === '/cast_log') {
    return {
      logs: [
        '[' + new Date().toLocaleTimeString() + '] info: API iniciada em http://127.0.0.1:8769',
        '[' + new Date().toLocaleTimeString() + '] scan: 2 dispositivos encontrados na rede',
        '[' + new Date().toLocaleTimeString() + '] info: Catalogo M3U carregado (v' + mockVersion + ')',
      ],
    } as unknown as T;
  }

  throw new Error(`Endpoint não encontrado no mock: ${path}`);
}
