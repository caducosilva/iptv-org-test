import React, { useState } from 'react';
import {
  HealthResponse,
  ProbeStatusResponse,
} from '../types';
import { getBaseUrl, setBaseUrl, getIsMockMode, setMockMode } from '../services/api';
import { Settings, RefreshCw, Cpu, Folder, Activity, Zap, CheckCircle2, HelpCircle, XCircle, Star, HelpCircle as QuestionIcon } from 'lucide-react';

interface HeaderProps {
  health: HealthResponse | null;
  probeStatus: ProbeStatusResponse | null;
  apiConnected: boolean;
  catalogVersion: number;
  folderPath: string;
  onRefreshAll: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  probeStatus,
  apiConnected,
  catalogVersion,
  folderPath,
  onRefreshAll,
}) => {
  const [showSettings, setShowSettings] = useState(false);
  const [inputUrl, setInputUrl] = useState(getBaseUrl());
  const [isMock, setIsMock] = useState(getIsMockMode());

  const handleSaveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    setBaseUrl(inputUrl);
    setMockMode(isMock);
    setShowSettings(false);
    onRefreshAll();
  };

  const counts = probeStatus?.stats?.counts || {
    ok: 0,
    doubt: 0,
    dead: 0,
    confirmed: 0,
    unknown: 0,
  };

  const probe = probeStatus?.probe;
  const isProbing = probe?.running;
  const probeProgress = probe?.total ? Math.round((probe.done / probe.total) * 100) : 0;

  return (
    <header className="bg-slate-900 border-b border-slate-800 text-slate-100 p-3 sm:p-4 sticky top-0 z-30 shadow-md">
      <div className="max-w-7xl mx-auto flex flex-col gap-3">
        {/* Top Row: Title, API status & Settings */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-600/20 text-indigo-400 rounded-lg border border-indigo-500/30">
              <Zap className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold tracking-tight text-white">IPTV Cast Companion</h1>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-mono">
                  v{catalogVersion || 1}
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                Painel de Transmissao e Diagnostico Local
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* API Connection Badge */}
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium border ${
                apiConnected
                  ? isMock
                    ? 'bg-amber-950/40 border-amber-800/60 text-amber-300'
                    : 'bg-emerald-950/40 border-emerald-800/60 text-emerald-400'
                  : 'bg-rose-950/40 border-rose-800/60 text-rose-400'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  apiConnected
                    ? isMock
                      ? 'bg-amber-400 animate-pulse'
                      : 'bg-emerald-400 animate-pulse'
                    : 'bg-rose-500'
                }`}
              />
              <span>
                {apiConnected
                  ? isMock
                    ? 'MODO SIMULACAO'
                    : 'API ONLINE'
                  : 'API OFFLINE'}
              </span>
            </div>

            <button
              onClick={onRefreshAll}
              className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
              title="Atualizar TUDO"
            >
              <RefreshCw className="w-4 h-4" />
            </button>

            <button
              onClick={() => setShowSettings(!showSettings)}
              className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
              title="Configuracoes da API"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Settings Dropdown Panel */}
        {showSettings && (
          <form
            onSubmit={handleSaveSettings}
            className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-xs flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between"
          >
            <div className="flex-1 w-full space-y-1">
              <label className="text-slate-400 font-semibold block">URL da API Companion Local</label>
              <input
                type="text"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200 font-mono text-xs focus:outline-none focus:border-indigo-500"
                placeholder="http://127.0.0.1:8769"
              />
            </div>

            <div className="flex items-center gap-2 self-end sm:self-center">
              <label className="flex items-center gap-1.5 text-slate-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={isMock}
                  onChange={(e) => setIsMock(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0"
                />
                <span>Modo de Teste / Simulação sem backend local</span>
              </label>

              <button
                type="submit"
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium transition"
              >
                Salvar
              </button>
            </div>
          </form>
        )}

        {/* Second Row: Info stats & Health counts */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs">
          {/* PC IP & Folder */}
          <div className="col-span-2 md:col-span-2 bg-slate-950/70 p-2 rounded border border-slate-800/80 flex flex-col justify-between">
            <div className="flex items-center justify-between text-slate-400">
              <span className="flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-indigo-400" /> IP Local PC:
              </span>
              <span className="font-mono text-slate-200 font-semibold">{health?.ip || '127.0.0.1'}</span>
            </div>
            <div className="flex items-center justify-between text-slate-400 mt-1">
              <span className="flex items-center gap-1 truncate">
                <Folder className="w-3.5 h-3.5 text-amber-400 shrink-0" /> Pasta M3U:
              </span>
              <span className="font-mono text-slate-300 text-[11px] truncate max-w-[150px] sm:max-w-[200px]" title={folderPath}>
                {folderPath || 'Nao identificada'}
              </span>
            </div>
          </div>

          {/* Health Counters */}
          <div className="col-span-2 md:col-span-4 bg-slate-950/70 p-2 rounded border border-slate-800/80 flex items-center justify-between gap-1 overflow-x-auto">
            <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-amber-950/30 border border-amber-900/40 text-amber-300">
              <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400/20" />
              <div className="leading-none">
                <div className="text-[10px] text-amber-400/80 font-medium uppercase">CONFIRMADO</div>
                <div className="font-bold text-sm font-mono">{counts.confirmed}</div>
              </div>
            </div>

            <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-emerald-950/30 border border-emerald-900/40 text-emerald-300">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <div className="leading-none">
                <div className="text-[10px] text-emerald-400/80 font-medium uppercase">OK</div>
                <div className="font-bold text-sm font-mono">{counts.ok}</div>
              </div>
            </div>

            <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-yellow-950/30 border border-yellow-900/40 text-yellow-300">
              <HelpCircle className="w-3.5 h-3.5 text-yellow-400" />
              <div className="leading-none">
                <div className="text-[10px] text-yellow-400/80 font-medium uppercase">DUVIDA</div>
                <div className="font-bold text-sm font-mono">{counts.doubt}</div>
              </div>
            </div>

            <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-rose-950/30 border border-rose-900/40 text-rose-300">
              <XCircle className="w-3.5 h-3.5 text-rose-400" />
              <div className="leading-none">
                <div className="text-[10px] text-rose-400/80 font-medium uppercase">MORTO</div>
                <div className="font-bold text-sm font-mono">{counts.dead}</div>
              </div>
            </div>

            <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-slate-900 border border-slate-800 text-slate-400">
              <QuestionIcon className="w-3.5 h-3.5 text-slate-500" />
              <div className="leading-none">
                <div className="text-[10px] text-slate-500 font-medium uppercase">UNKNOWN</div>
                <div className="font-bold text-sm font-mono">{counts.unknown}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Probe Background Progress Bar if Probing */}
        {isProbing && (
          <div className="bg-indigo-950/60 border border-indigo-800/50 rounded p-2 text-xs text-indigo-200">
            <div className="flex items-center justify-between mb-1 font-medium">
              <span className="flex items-center gap-2">
                <Activity className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
                Teste de Saude em Andamento (Probe Background)
              </span>
              <span className="font-mono text-indigo-300">
                {probe.done} / {probe.total} ({probeProgress}%)
              </span>
            </div>
            <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-indigo-500 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${probeProgress}%` }}
              />
            </div>
            {probe.last_url && (
              <p className="text-[10px] text-indigo-300/70 font-mono truncate mt-1">
                Avaliando: {probe.last_url}
              </p>
            )}
          </div>
        )}
      </div>
    </header>
  );
};
