export type HealthStatus = 'ok' | 'doubt' | 'dead' | 'confirmed' | 'unknown';

export interface Channel {
  name: string;
  url: string;
  playlist: string;
  group?: string;
  /** codigo ISO-2 do pais principal (vem do tvg-id da lista M3U), ex.: 'br' */
  country?: string;
  /**
   * Todos os paises em que o canal aparece. Um canal internacional que esta
   * dentro da lista do Brasil (A&E Brasil, por exemplo) fica em ['us','br'].
   */
  countries?: string[];
  /** tvg-logo do canal, quando a lista informa */
  logo?: string;
  score?: number;
  signalStrength?: number; // 0 to 100%
  codecs?: string[];
  bitrate?: string;
  health: HealthStatus;
  health_fail?: number;
  health_error?: string;
  confirmed?: boolean;
}

export interface ToastNotification {
  id: string;
  title: string;
  message: string;
  type: 'fallback' | 'info' | 'warning' | 'success';
}

export interface Playlist {
  name: string;
  file: string;
  count: number;
  mtime: number;
}

export interface HealthCounts {
  ok: number;
  doubt: number;
  dead: number;
  confirmed: number;
  unknown: number;
}

export interface CastInfo {
  phase: 'idle' | 'scan' | 'started' | 'running' | 'success' | 'error';
  ok: boolean;
  message: string;
  device: string | null;
  url: string | null;
  title: string | null;
  updatedAt: string | null;
}

export interface HealthResponse {
  ok: boolean;
  ip: string;
  devices: number;
  cast: CastInfo;
  pending: boolean;
}

export interface Device {
  friendlyName: string;
  host: string;
  type?: string;
  manufacturer?: string;
  modelName?: string;
  /** backend marca se o aparelho aceita transmissao (TV/Chromecast, nao roteador) */
  castable?: boolean;
  /** porta de cast respondeu agora (TV ligada, fora do standby) */
  reachable?: boolean;
  /** roteador / WPS e afins, mostrados so em modo avancado */
  isJunk?: boolean;
  /** TV ja conhecida que nao apareceu no scan atual (standby/desligada) */
  offline?: boolean;
  lastSeen?: string;
  avt_control?: string;
}

export interface DevicesResponse {
  devices: Device[];
}

export interface ScanResponse {
  count: number;
  castable?: number;
  devices: Device[];
}

export interface PlaylistsResponse {
  playlists: Playlist[];
  version: number;
  folder: string;
}

export interface CatalogResponse {
  changed: boolean;
  version: number;
  folder: string;
  playlists: number;
  channels: number;
}

export interface ChannelsResponse {
  query: string;
  playlist: string;
  count: number;
  channels: Channel[];
  version: number;
  folder: string;
  hide_dead: boolean;
  health: {
    counts: HealthCounts;
  };
}

export interface PreviewResponse {
  ok: boolean;
  url: string;
  contentType?: string;
  bytes?: number;
  hls?: boolean;
  fail_class?: 'ok' | 'soft' | 'hard';
  health?: HealthStatus;
  health_entry?: {
    status: HealthStatus;
    fail_count: number;
  };
  error?: string;
}

export interface ProbeStats {
  running: boolean;
  paused: boolean;
  done: number;
  total: number;
  ok: number;
  doubt: number;
  dead: number;
  errors: number;
  last_url: string;
  last_message: string;
  started_at: string;
}

export interface ProbeStatusResponse {
  stats: {
    counts: HealthCounts;
  };
  probe: ProbeStats;
}

export interface CastRequestBody {
  url: string;
  title: string;
  channelName: string;
  deviceName: string;
  host: string;
  deviceLabel: string;
}

export interface CastResponse {
  ok: boolean;
  started: boolean;
  pending: boolean;
  device?: string;
  host?: string;
  url?: string;
  title?: string;
  message?: string;
  error?: string;
  hint?: string;
}

/**
 * Etapas reais reportadas pelo worker de cast, na ordem em que acontecem.
 * O painel usa isso para mostrar em que ponto o espelhamento está.
 */
export type CastPhase =
  | 'idle'
  | 'queued'
  | 'preflight'
  | 'connecting'
  | 'connected'
  | 'launching'
  | 'loading'
  | 'buffering'
  | 'success'
  | 'error'
  | 'started'
  | 'running'
  | 'scan';

export interface CastStatusResponse {
  pending: boolean;
  ok: boolean;
  phase: CastPhase;
  message: string;
  error: string | null;
  device: string | null;
  host: string | null;
  url: string | null;
  source_url: string | null;
  title: string | null;
  player?: 'PLAYING' | 'BUFFERING' | 'IDLE' | string;
  content_id?: string;
  app?: string;
  logs?: string[];
  /** 'tv_offline' | 'device_not_castable' - permite mensagem de ajuda especifica */
  hint?: string;
  started_at?: string;
  progress_at?: string;
  finished_at?: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  phase: 'info' | 'scan' | 'started' | 'running' | 'success' | 'error' | 'probe';
  message: string;
}
