import React from 'react';
import { Channel, PreviewResponse } from '../types';
import { Tv, CheckCircle2, AlertTriangle, Globe, Radio, MonitorPlay } from 'lucide-react';
import { ChannelPlayer } from './ChannelPlayer';
import { grupoValido } from './ChannelList';

interface PreviewPanelProps {
  channel: Channel | null;
  preview: PreviewResponse | null;
  isLoading: boolean;
}

export const PreviewPanel: React.FC<PreviewPanelProps> = ({
  channel,
  preview,
  isLoading,
}) => {
  if (!channel) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 text-center text-slate-500 flex flex-col items-center justify-center min-h-[160px]">
        <Tv className="w-8 h-8 text-slate-700 mb-2" />
        <p className="text-xs font-semibold text-slate-400">Nenhum canal selecionado</p>
        <p className="text-[11px] text-slate-600 mt-0.5">
          Clique em um canal da lista para assistir aqui no PC.
        </p>
      </div>
    );
  }

  const isOk = preview?.ok ?? (channel.health === 'ok' || channel.health === 'confirmed');
  const errorMsg = preview?.error || channel.health_error;
  const signal = channel.signalStrength ?? channel.score ?? (isOk ? 90 : 15);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 sm:p-4 space-y-3">
      {/* Title Bar */}
      <div className="flex items-start justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider flex items-center gap-1">
              <MonitorPlay className="w-3 h-3" />
              Assistindo no PC
            </span>
            {/* Signal gauge */}
            <span
              className={`px-1.5 py-0.2 rounded text-[10px] font-mono font-bold flex items-center gap-1 border ${
                signal >= 70
                  ? 'bg-emerald-950/80 border-emerald-800 text-emerald-300'
                  : signal >= 30
                  ? 'bg-yellow-950/80 border-yellow-800 text-yellow-300'
                  : 'bg-rose-950/80 border-rose-800 text-rose-300'
              }`}
            >
              <Radio className="w-3 h-3" />
              Sinal: {signal}%
            </span>
          </div>
          <h3 className="text-sm font-bold text-white leading-snug mt-0.5">{channel.name}</h3>
          <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-1">
            <span className="font-mono bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">
              {channel.playlist}
            </span>
            {grupoValido(channel.group) && (
              <span className="bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800 font-medium text-slate-300">
                {grupoValido(channel.group)}
              </span>
            )}
          </div>
        </div>

        {/* Status Badge */}
        <div>
          {isLoading ? (
            <span className="px-2.5 py-1 bg-indigo-950/80 border border-indigo-700 text-indigo-300 rounded text-xs font-mono font-medium flex items-center gap-1.5 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-spin" />
              Testando...
            </span>
          ) : isOk ? (
            <span className="px-2.5 py-1 bg-emerald-950/80 border border-emerald-700 text-emerald-300 rounded text-xs font-mono font-bold flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              SINAL OK
            </span>
          ) : (
            <span className="px-2.5 py-1 bg-rose-950/80 border border-rose-700 text-rose-300 rounded text-xs font-mono font-bold flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
              SEM SINAL
            </span>
          )}
        </div>
      </div>

      {/* Player real do app (independente do canal que vai para a TV) */}
      <div className="bg-slate-950 rounded-md border border-slate-800 p-2 text-xs space-y-2">
        <ChannelPlayer channel={channel} />

        {!isOk && (
          <div className="p-2 bg-rose-950/30 border border-rose-900/40 rounded text-rose-300 space-y-0.5">
            <div className="font-semibold text-[11px] flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
              O teste de sinal falhou ({signal}%)
            </div>
            <p className="text-[10px] text-rose-200/80 font-mono break-words">
              {errorMsg || 'O servidor do canal não respondeu'}
            </p>
          </div>
        )}

        {isLoading && (
          <p className="text-[10px] text-slate-500 font-mono flex items-center gap-1.5">
            <span className="w-3 h-3 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            Testando o sinal do canal...
          </p>
        )}
      </div>

      {/* URL display (truncated) */}
      <div className="bg-slate-950 p-2 rounded border border-slate-800/80 text-[11px] font-mono text-slate-400 flex items-center gap-2">
        <Globe className="w-3.5 h-3.5 text-slate-500 shrink-0" />
        <span className="truncate flex-1 text-slate-300" title={channel.url}>
          {channel.url}
        </span>
      </div>
    </div>
  );
};
