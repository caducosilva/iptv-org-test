import React, { useEffect, useRef, useState, useCallback } from 'react';
import Hls from 'hls.js';
import { Channel } from '../types';
import { Play, Loader2, AlertTriangle, RotateCw, Volume2, VolumeX, Maximize2 } from 'lucide-react';
import { getBaseUrl } from '../services/api';

interface ChannelPlayerProps {
  channel: Channel | null;
  /** true quando o canal ja falhou no teste de sinal */
  disabled?: boolean;
}

type PlayerState = 'idle' | 'loading' | 'playing' | 'error';

/**
 * Player HLS real do app (independente do que esta indo para a TV).
 *
 * O stream passa pelo /proxy_media do backend: os servidores de IPTV nao
 * mandam Access-Control-Allow-Origin, entao o navegador bloquearia o fetch
 * direto. O proxy tambem reescreve a playlist para os segmentos virem por ele.
 */
export const ChannelPlayer: React.FC<ChannelPlayerProps> = ({ channel, disabled }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const [state, setState] = useState<PlayerState>('idle');
  const [error, setError] = useState<string>('');
  const [muted, setMuted] = useState(true);
  const [attempt, setAttempt] = useState(0);

  const proxied = channel
    ? `${getBaseUrl()}/proxy_media?url=${encodeURIComponent(channel.url)}`
    : '';

  const destroy = useCallback(() => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
  }, []);

  // Troca de canal para o app: derruba o player anterior e monta o novo.
  // Isso NAO toca no que esta sendo espelhado na TV (sao fluxos separados).
  useEffect(() => {
    destroy();
    setError('');

    const video = videoRef.current;
    if (!video || !channel || !proxied) {
      setState('idle');
      return;
    }

    setState('loading');

    if (Hls.isSupported()) {
      const hls = new Hls({
        lowLatencyMode: false,
        enableWorker: true,
        manifestLoadingTimeOut: 20000,
        manifestLoadingMaxRetry: 2,
        fragLoadingTimeOut: 30000,
        fragLoadingMaxRetry: 3,
        maxBufferLength: 20,
        backBufferLength: 30,
      });
      hlsRef.current = hls;

      hls.loadSource(proxied);
      hls.attachMedia(video);

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {
          // autoplay bloqueado: o usuario aperta o play do proprio video
        });
      });

      hls.on(Hls.Events.ERROR, (_evt, data) => {
        if (!data.fatal) return;
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            setError('Falha de rede ao buscar o canal. O servidor do canal pode estar fora do ar.');
            break;
          case Hls.ErrorTypes.MEDIA_ERROR:
            // erro de midia costuma ter recuperacao
            try {
              hls.recoverMediaError();
              return;
            } catch {
              setError('Formato de vídeo não suportado pelo navegador.');
            }
            break;
          default:
            setError(data.details || 'Não foi possível reproduzir este canal.');
        }
        setState('error');
        hls.destroy();
        hlsRef.current = null;
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari toca HLS nativo
      video.src = proxied;
      video.play().catch(() => undefined);
    } else {
      setError('Este navegador não suporta HLS.');
      setState('error');
    }

    return destroy;
  }, [proxied, channel, destroy, attempt]);

  useEffect(() => () => destroy(), [destroy]);

  const handleRetry = () => {
    setError('');
    setState('loading');
    setAttempt((a) => a + 1);
  };

  const toggleMute = () => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setMuted(video.muted);
  };

  const goFullscreen = () => {
    videoRef.current?.requestFullscreen?.().catch(() => undefined);
  };

  if (!channel) {
    return (
      <div className="aspect-video bg-black rounded border border-slate-800 flex flex-col items-center justify-center text-slate-600 gap-1.5">
        <Play className="w-7 h-7" />
        <p className="text-[11px] font-semibold text-slate-500">Escolha um canal para assistir aqui</p>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="relative aspect-video bg-black rounded border border-slate-800 overflow-hidden">
        <video
          ref={videoRef}
          controls
          autoPlay
          muted={muted}
          playsInline
          onPlaying={() => {
            setState('playing');
            setError('');
          }}
          onWaiting={() => setState('loading')}
          className="w-full h-full object-contain bg-black"
        />

        {state === 'loading' && !error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/70 pointer-events-none">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
            <span className="text-[11px] font-mono text-slate-300">Carregando o canal...</span>
          </div>
        )}

        {state === 'error' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/85 p-4 text-center">
            <AlertTriangle className="w-6 h-6 text-rose-400" />
            <p className="text-[11px] text-rose-200 leading-snug max-w-xs">{error}</p>
            <button
              onClick={handleRetry}
              className="mt-1 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 active:scale-95 border border-slate-700 text-[11px] text-slate-200 font-semibold flex items-center gap-1.5 transition-transform duration-100"
            >
              <RotateCw className="w-3.5 h-3.5" />
              Tentar de novo
            </button>
          </div>
        )}

        {state === 'playing' && (
          <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/80 text-emerald-400 font-mono text-[10px] font-bold flex items-center gap-1 border border-emerald-800/60 pointer-events-none">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            AO VIVO NO APP
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-mono text-slate-500 truncate flex-1" title={channel.name}>
          {channel.name}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={toggleMute}
            className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 active:scale-90 border border-slate-700 text-slate-300 transition-transform duration-100"
            title={muted ? 'Ativar som' : 'Silenciar'}
          >
            {muted ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5 text-emerald-400" />}
          </button>
          <button
            onClick={goFullscreen}
            className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 active:scale-90 border border-slate-700 text-slate-300 transition-transform duration-100"
            title="Tela cheia"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
