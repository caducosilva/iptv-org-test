import React, { useRef, useEffect } from 'react';
import { LogEntry } from '../types';
import { Terminal, Trash2, RefreshCw } from 'lucide-react';

interface LiveLogProps {
  logs: LogEntry[];
  onClearLogs: () => void;
  onRefreshLogs: () => void;
  isRefreshing: boolean;
}

export const LiveLog: React.FC<LiveLogProps> = ({
  logs,
  onClearLogs,
  onRefreshLogs,
  isRefreshing,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new log comes
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  const getPhaseBadgeColor = (phase: string) => {
    switch (phase) {
      case 'success':
        return 'text-emerald-400 font-bold';
      case 'error':
        return 'text-rose-400 font-bold';
      case 'started':
      case 'running':
        return 'text-amber-400 font-semibold';
      case 'scan':
        return 'text-cyan-400 font-semibold';
      case 'probe':
        return 'text-indigo-400 font-semibold';
      default:
        return 'text-slate-400 font-normal';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-2 flex flex-col h-56">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2 shrink-0">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
          <Terminal className="w-4 h-4 text-indigo-400" />
          <span>Console de Log Ao Vivo</span>
          <span className="text-[10px] text-slate-500 font-mono">({logs.length} entradas)</span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={onRefreshLogs}
            disabled={isRefreshing}
            className="p-1 text-slate-400 hover:text-slate-200 bg-slate-950 rounded border border-slate-800 transition"
            title="Atualizar Logs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={onClearLogs}
            className="p-1 text-slate-400 hover:text-rose-400 bg-slate-950 rounded border border-slate-800 transition"
            title="Limpar Console"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Log Console Body */}
      <div
        ref={containerRef}
        className="flex-1 bg-slate-950 border border-slate-800 rounded p-2.5 font-mono text-[11px] overflow-y-auto space-y-1 select-text"
      >
        {logs.length === 0 ? (
          <p className="text-slate-600 italic">Nenhum evento registrado ainda.</p>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="leading-tight break-all flex items-start gap-1.5">
              <span className="text-slate-600 shrink-0">[{log.timestamp}]</span>
              <span className={`shrink-0 uppercase text-[10px] px-1 rounded bg-slate-900 border border-slate-800 ${getPhaseBadgeColor(log.phase)}`}>
                {log.phase}
              </span>
              <span className="text-slate-300">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
