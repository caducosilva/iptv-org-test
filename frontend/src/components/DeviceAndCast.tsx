import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Device, Channel, CastStatusResponse, CastPhase } from '../types';
import {
  Tv,
  RefreshCw,
  Cast,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Radio,
  MonitorPlay,
  Search,
  X,
  PowerOff,
  Wifi,
  Square,
} from 'lucide-react';

interface DeviceAndCastProps {
  devices: Device[];
  selectedDevice: Device | null;
  onSelectDevice: (device: Device) => void;
  onRescanDevices: () => void;
  isScanningDevices: boolean;
  castChannel: Channel | null;
  channels: Channel[];
  onSelectCastChannel: (channel: Channel) => void;
  onStartCast: (device: Device, channel: Channel) => void;
  onStopCast: () => void;
  isCastPending: boolean;
  castStatus: CastStatusResponse | null;
  appChannel: Channel | null;
}

/** Etapas do espelhamento, na ordem real em que o backend as reporta. */
const STEPS = [
  { key: 'preflight', label: 'Canal', hint: 'Testando o link' },
  { key: 'connecting', label: 'Conectando', hint: 'Falando com a TV' },
  { key: 'connected', label: 'TV pronta', hint: 'Player aberto' },
  { key: 'loading', label: 'Enviando', hint: 'Mandando o canal' },
  { key: 'playing', label: 'No ar', hint: 'Espelhando' },
] as const;

const PHASE_STEP: Record<string, number> = {
  queued: 0,
  preflight: 0,
  started: 0,
  connecting: 1,
  running: 1,
  connected: 2,
  launching: 2,
  loading: 3,
  buffering: 3,
  success: 4,
};

function stepIndexFor(phase: CastPhase | undefined): number {
  if (!phase) return 0;
  return PHASE_STEP[phase] ?? 0;
}

export const DeviceAndCast: React.FC<DeviceAndCastProps> = ({
  devices,
  selectedDevice,
  onSelectDevice,
  onRescanDevices,
  isScanningDevices,
  castChannel,
  channels,
  onSelectCastChannel,
  onStartCast,
  onStopCast,
  isCastPending,
  castStatus,
  appChannel,
}) => {
  const [elapsed, setElapsed] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState('');
  const [showAllDevices, setShowAllDevices] = useState(false);
  const [justPressed, setJustPressed] = useState(false);
  const pickerInputRef = useRef<HTMLInputElement>(null);

  // Cronometro do envio
  useEffect(() => {
    if (!isCastPending) {
      setElapsed(0);
      return;
    }
    setElapsed(0);
    const started = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 250);
    return () => clearInterval(interval);
  }, [isCastPending]);

  // Feedback tatil imediato ao clicar (nao espera a rede)
  useEffect(() => {
    if (!justPressed) return;
    const t = setTimeout(() => setJustPressed(false), 220);
    return () => clearTimeout(t);
  }, [justPressed]);

  useEffect(() => {
    if (pickerOpen) pickerInputRef.current?.focus();
  }, [pickerOpen]);

  // Roteador/WPS ficam escondidos: nao aceitam transmissao
  const castableDevices = useMemo(
    () => devices.filter((d) => d.castable !== false),
    [devices]
  );
  const visibleDevices = showAllDevices ? devices : castableDevices;
  const hiddenCount = devices.length - castableDevices.length;

  // Lista do seletor de canal limitada: 5000 <option> travavam a interface
  const pickerResults = useMemo(() => {
    const q = pickerQuery.trim().toLowerCase();
    const source = q
      ? channels.filter(
          (c) => c.name.toLowerCase().includes(q) || (c.group || '').toLowerCase().includes(q)
        )
      : channels;
    return source.slice(0, 40);
  }, [channels, pickerQuery]);

  const isSuccess = castStatus?.phase === 'success' && castStatus?.ok;
  const isError = castStatus?.phase === 'error' || Boolean(castStatus?.error);

  // 'error' nao tem etapa propria: guardamos a ultima etapa alcancada para
  // marcar exatamente ONDE parou (antes marcava sempre a primeira).
  const reachedStepRef = useRef(0);
  if (isCastPending && castStatus?.phase) {
    reachedStepRef.current = Math.max(reachedStepRef.current, stepIndexFor(castStatus.phase));
  }
  useEffect(() => {
    if (isCastPending) reachedStepRef.current = 0;
  }, [isCastPending]);

  const currentStep = isError
    ? reachedStepRef.current
    : isSuccess
    ? STEPS.length - 1
    : stepIndexFor(castStatus?.phase);
  const showStepper = isCastPending || isSuccess || isError;

  const deviceOffline = selectedDevice && selectedDevice.reachable === false;
  const canCast = Boolean(castChannel && selectedDevice && !isCastPending);

  let castButtonText = 'Escolha um canal para espelhar';
  if (isCastPending) {
    castButtonText = `ESPELHANDO... ${elapsed}s`;
  } else if (castChannel && selectedDevice) {
    castButtonText = 'ESPELHAR NA TV';
  } else if (castChannel && !selectedDevice) {
    castButtonText = 'Nenhuma TV encontrada';
  }

  const handleCastClick = () => {
    setJustPressed(true);
    if (selectedDevice && castChannel) {
      onStartCast(selectedDevice, castChannel);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 sm:p-4 space-y-3.5 font-sans">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2">
          <Tv className="w-4 h-4 text-indigo-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-white">Espelhar na TV</h3>
        </div>

        <button
          onClick={onRescanDevices}
          disabled={isScanningDevices}
          className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 active:scale-95 disabled:opacity-50 text-slate-300 text-xs font-medium rounded border border-slate-700 flex items-center gap-1.5 transition-transform duration-100"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-indigo-400 ${isScanningDevices ? 'animate-spin' : ''}`} />
          {isScanningDevices ? 'Procurando (~11s)...' : 'Procurar TVs'}
        </button>
      </div>

      {/* 1. TV de destino */}
      <div>
        <label className="text-[11px] text-slate-400 font-semibold block mb-1">1. TV de destino</label>

        {visibleDevices.length === 0 ? (
          <div className="p-3 bg-slate-950 rounded border border-slate-800 text-xs text-slate-400 space-y-1.5">
            <p className="font-semibold text-amber-300 flex items-center gap-1.5">
              <PowerOff className="w-3.5 h-3.5" />
              Nenhuma TV encontrada
            </p>
            <p className="text-[11px] leading-snug text-slate-400">
              Ligue a TV (não basta o standby), confirme que ela está no mesmo Wi-Fi e clique em
              &quot;Procurar TVs&quot;.
            </p>
          </div>
        ) : (
          <>
            <select
              value={selectedDevice?.host || ''}
              onChange={(e) => {
                const dev = devices.find((d) => d.host === e.target.value);
                if (dev) onSelectDevice(dev);
              }}
              className="w-full bg-slate-950 border border-slate-700 rounded-md p-2 text-xs text-slate-100 font-mono font-medium focus:outline-none focus:border-indigo-500 transition cursor-pointer"
            >
              {visibleDevices.map((dev) => (
                <option key={dev.host} value={dev.host}>
                  {dev.reachable ? '🟢' : '⚪'} {dev.friendlyName} @ {dev.host}
                </option>
              ))}
            </select>

            {deviceOffline && (
              <div className="mt-1 p-2 rounded bg-amber-950/40 border border-amber-800/70">
                <p className="text-[10px] text-amber-200 flex items-start gap-1 leading-snug font-semibold">
                  <PowerOff className="w-3 h-3 shrink-0 mt-0.5" />
                  TV desligada ou em standby — ela não respondeu agora.
                </p>
                <p className="text-[10px] text-amber-300/80 mt-1 leading-snug">
                  Ligue a TV pelo controle e clique em &quot;Procurar TVs&quot;. Você pode deixar tudo
                  pronto aqui e só apertar Espelhar depois.
                </p>
              </div>
            )}
            {!deviceOffline && selectedDevice?.reachable && (
              <p className="text-[10px] text-emerald-300/90 mt-1 flex items-center gap-1">
                <Wifi className="w-3 h-3 shrink-0" />
                TV ligada e pronta para receber.
              </p>
            )}
            {hiddenCount > 0 && (
              <button
                onClick={() => setShowAllDevices((v) => !v)}
                className="text-[10px] text-slate-500 hover:text-slate-300 mt-1 underline transition"
              >
                {showAllDevices
                  ? 'Ocultar aparelhos que não aceitam transmissão'
                  : `Mostrar ${hiddenCount} aparelho(s) que não aceitam transmissão`}
              </button>
            )}
          </>
        )}
      </div>

      {/* 2. Canal que vai para a TV */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-[11px] text-slate-400 font-semibold">2. Canal que vai para a TV</label>
          {castChannel && (
            <span className="px-1.5 py-0.5 rounded bg-indigo-950 border border-indigo-800 text-indigo-300 text-[10px] font-mono flex items-center gap-1">
              <Radio className="w-3 h-3 text-emerald-400" />
              {castChannel.signalStrength ?? castChannel.score ?? 80}%
            </span>
          )}
        </div>

        <button
          onClick={() => setPickerOpen((v) => !v)}
          className="w-full bg-slate-950 border border-indigo-700/80 hover:border-indigo-500 active:scale-[0.99] rounded-md p-2 text-xs text-left text-indigo-100 font-semibold flex items-center justify-between gap-2 transition-transform duration-100"
        >
          <span className="truncate">
            {castChannel ? castChannel.name : '-- Selecione o canal da TV --'}
          </span>
          <Search className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
        </button>

        {pickerOpen && (
          <div className="mt-1 border border-slate-700 rounded-md bg-slate-950 overflow-hidden">
            <div className="flex items-center gap-1.5 p-1.5 border-b border-slate-800">
              <Search className="w-3.5 h-3.5 text-slate-500 shrink-0" />
              <input
                ref={pickerInputRef}
                value={pickerQuery}
                onChange={(e) => setPickerQuery(e.target.value)}
                placeholder="Buscar canal..."
                className="flex-1 bg-transparent text-xs text-slate-100 focus:outline-none placeholder:text-slate-600"
              />
              <button
                onClick={() => {
                  setPickerOpen(false);
                  setPickerQuery('');
                }}
                className="p-0.5 text-slate-500 hover:text-slate-200 transition"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="max-h-52 overflow-y-auto">
              {pickerResults.length === 0 ? (
                <p className="p-3 text-[11px] text-slate-500 text-center">Nenhum canal encontrado.</p>
              ) : (
                pickerResults.map((c) => (
                  <button
                    key={`${c.name}|||${c.url}`}
                    onClick={() => {
                      onSelectCastChannel(c);
                      setPickerOpen(false);
                      setPickerQuery('');
                    }}
                    className="w-full px-2.5 py-1.5 text-left text-[11px] text-slate-200 hover:bg-indigo-950/70 active:bg-indigo-900 flex items-center justify-between gap-2 transition-colors border-b border-slate-900/80 last:border-0"
                  >
                    <span className="truncate">{c.name}</span>
                    <span className="font-mono text-[10px] text-slate-500 shrink-0">
                      {c.signalStrength ?? c.score ?? 80}%
                    </span>
                  </button>
                ))
              )}
              {channels.length > pickerResults.length && (
                <p className="px-2.5 py-1.5 text-[10px] text-slate-600 text-center">
                  Mostrando {pickerResults.length} de {channels.length}. Refine a busca.
                </p>
              )}
            </div>
          </div>
        )}

        {appChannel && castChannel && appChannel.url !== castChannel.url && (
          <p className="text-[10px] text-slate-400 font-mono mt-1 truncate">
            App: <span className="text-white">{appChannel.name}</span> · TV:{' '}
            <span className="text-emerald-300">{castChannel.name}</span>
          </p>
        )}
      </div>

      {/* 3. Botao principal */}
      <div className="space-y-2">
        <button
          onClick={handleCastClick}
          disabled={!canCast}
          aria-busy={isCastPending}
          className={`w-full py-3.5 px-4 rounded-lg font-bold text-sm flex items-center justify-center gap-2 shadow-lg transition-all duration-100 ${
            justPressed ? 'scale-[0.97]' : 'scale-100'
          } ${
            isCastPending
              ? 'bg-amber-600 text-white cursor-wait'
              : !canCast
              ? 'bg-slate-800 text-slate-500 border border-slate-700/50 cursor-not-allowed'
              : 'bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white border border-emerald-400 hover:shadow-emerald-900/40'
          }`}
        >
          {isCastPending ? (
            <Loader2 className="w-5 h-5 animate-spin text-white shrink-0" />
          ) : (
            <Cast className="w-5 h-5 shrink-0" />
          )}
          <span className="truncate">{castButtonText}</span>
        </button>

        {isCastPending && (
          <button
            onClick={onStopCast}
            className="w-full py-1.5 rounded-md bg-slate-800 hover:bg-rose-900/60 active:scale-[0.98] text-slate-300 hover:text-rose-200 text-[11px] font-semibold border border-slate-700 hover:border-rose-800 flex items-center justify-center gap-1.5 transition-all duration-100"
          >
            <Square className="w-3 h-3" />
            Cancelar envio
          </button>
        )}

        {isSuccess && castChannel && (
          <button
            onClick={onStopCast}
            className="w-full py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 active:scale-[0.98] text-slate-300 text-[11px] font-semibold border border-slate-700 flex items-center justify-center gap-1.5 transition-all duration-100"
          >
            <Square className="w-3 h-3" />
            Parar transmissão
          </button>
        )}
      </div>

      {/* 4. Etapas do espelhamento */}
      {showStepper && (
        <div className="space-y-2 pt-0.5">
          <div className="flex items-stretch gap-1">
            {STEPS.map((step, idx) => {
              const done = isSuccess || idx < currentStep;
              const active = !isSuccess && !isError && idx === currentStep;
              const failed = isError && idx === currentStep;
              return (
                <div key={step.key} className="flex-1 min-w-0">
                  <div
                    className={`h-1 rounded-full transition-colors duration-300 ${
                      failed
                        ? 'bg-rose-500'
                        : done
                        ? 'bg-emerald-500'
                        : active
                        ? 'bg-amber-400 animate-pulse'
                        : 'bg-slate-800'
                    }`}
                  />
                  <p
                    className={`text-[9px] mt-1 text-center leading-tight truncate transition-colors ${
                      failed
                        ? 'text-rose-300 font-bold'
                        : done
                        ? 'text-emerald-300 font-semibold'
                        : active
                        ? 'text-amber-200 font-bold'
                        : 'text-slate-600'
                    }`}
                    title={step.hint}
                  >
                    {step.label}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 5. Status detalhado */}
      {castStatus && (
        <div
          className={`p-2.5 rounded-md border text-xs font-mono space-y-1 ${
            isSuccess
              ? 'bg-emerald-950/40 border-emerald-800/80 text-emerald-300'
              : isError
              ? 'bg-rose-950/40 border-rose-800/80 text-rose-300'
              : 'bg-indigo-950/40 border-indigo-800/80 text-indigo-300'
          }`}
        >
          <div className="flex items-center justify-between font-bold gap-2">
            <span className="flex items-center gap-1.5 uppercase text-[11px] truncate">
              {isSuccess ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              ) : isError ? (
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              ) : (
                <Loader2 className="w-4 h-4 animate-spin text-indigo-400 shrink-0" />
              )}
              {isSuccess ? 'Espelhando na TV' : isError ? 'Falhou' : castStatus.phase || 'em andamento'}
            </span>
            {castStatus.player && (
              <span className="px-1.5 py-0.5 bg-slate-900 rounded border border-slate-800 text-[10px] text-slate-200 shrink-0">
                {castStatus.player}
              </span>
            )}
          </div>

          <p className="text-[11px] leading-snug opacity-95 break-words">{castStatus.message}</p>

          {isSuccess && (
            <p className="text-[11px] text-emerald-200 font-sans font-semibold">
              Pode olhar a TV: {castStatus.title || castChannel?.name} deve estar no ar.
            </p>
          )}

          {castStatus.hint === 'tv_offline' && (
            <p className="text-[10px] text-amber-300 font-sans leading-snug">
              Dica: ligue a TV pelo controle, entre em qualquer app (Netflix/YouTube) uma vez e clique em
              &quot;Procurar TVs&quot;.
            </p>
          )}
        </div>
      )}

      {/* Explicacao do modo duplo */}
      <div className="p-2 bg-indigo-950/40 border border-indigo-900/60 rounded text-[10px] text-indigo-300/90 flex items-start gap-1.5">
        <MonitorPlay className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
        <span>
          Sintonização dupla: o canal da TV é independente do canal aberto no app.
        </span>
      </div>
    </div>
  );
};
