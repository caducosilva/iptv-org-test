import React from 'react';
import { HealthCounts } from '../types';
import { Activity, Info, ShieldCheck, AlertCircle, HelpCircle, XCircle, Star, CheckCircle2 } from 'lucide-react';

interface HealthPanelProps {
  counts: HealthCounts;
}

export const HealthPanel: React.FC<HealthPanelProps> = ({ counts }) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-3 text-xs text-slate-300">
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2 text-white font-bold">
        <Activity className="w-4 h-4 text-indigo-400" />
        <h3>Painel de Saude dos Canais &amp; Legenda de Diagnostico</h3>
      </div>

      {/* Counts Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 font-mono text-center">
        <div className="bg-slate-950 p-2 rounded border border-amber-900/40">
          <div className="text-[10px] text-amber-400 font-bold uppercase">CONFIRMADO [OK*]</div>
          <div className="text-lg font-bold text-amber-300">{counts.confirmed}</div>
        </div>
        <div className="bg-slate-950 p-2 rounded border border-emerald-900/40">
          <div className="text-[10px] text-emerald-400 font-bold uppercase">ONLINE [OK]</div>
          <div className="text-lg font-bold text-emerald-300">{counts.ok}</div>
        </div>
        <div className="bg-slate-950 p-2 rounded border border-yellow-900/40">
          <div className="text-[10px] text-yellow-400 font-bold uppercase">DUVIDA [?]</div>
          <div className="text-lg font-bold text-yellow-300">{counts.doubt}</div>
        </div>
        <div className="bg-slate-950 p-2 rounded border border-rose-900/40">
          <div className="text-[10px] text-rose-400 font-bold uppercase">MORTO [X]</div>
          <div className="text-lg font-bold text-rose-300">{counts.dead}</div>
        </div>
        <div className="bg-slate-950 p-2 rounded border border-slate-800 col-span-2 sm:col-span-1">
          <div className="text-[10px] text-slate-500 font-bold uppercase">UNKNOWN [&nbsp;]</div>
          <div className="text-lg font-bold text-slate-400">{counts.unknown}</div>
        </div>
      </div>

      {/* Rules & Help Legend */}
      <div className="bg-slate-950 p-3 rounded-md border border-slate-800 space-y-2 leading-relaxed">
        <div className="flex items-center gap-1.5 text-indigo-300 font-bold text-[11px] uppercase tracking-wide">
          <Info className="w-4 h-4 text-indigo-400 shrink-0" />
          Regras de Classificacao de Saude:
        </div>

        <ul className="space-y-1.5 text-[11px] text-slate-300 pl-1">
          <li className="flex items-start gap-2">
            <span className="px-1 py-0.2 bg-amber-950 border border-amber-800 text-amber-300 font-mono text-[10px] rounded font-bold shrink-0">
              [OK*]
            </span>
            <span>
              <strong className="text-amber-300">Confirmado por Cast:</strong> O canal já foi transmitido com sucesso para a TV. Por segurança, ele <span className="underline">nunca é escondido</span> no filtro &quot;Esconder mortos&quot;.
            </span>
          </li>

          <li className="flex items-start gap-2">
            <span className="px-1 py-0.2 bg-emerald-950 border border-emerald-800 text-emerald-400 font-mono text-[10px] rounded font-bold shrink-0">
              [OK]
            </span>
            <span>
              <strong className="text-emerald-400">Online:</strong> Respondeu rapidamente ao teste probe de stream HTTP.
            </span>
          </li>

          <li className="flex items-start gap-2">
            <span className="px-1 py-0.2 bg-yellow-950 border border-yellow-800 text-yellow-300 font-mono text-[10px] rounded font-bold shrink-0">
              [?]
            </span>
            <span>
              <strong className="text-yellow-300">Dúvida:</strong> Teve oscilação de timeout. Não é classificado como morto imediatamente para evitar falso positivo.
            </span>
          </li>

          <li className="flex items-start gap-2">
            <span className="px-1 py-0.2 bg-rose-950 border border-rose-800 text-rose-400 font-mono text-[10px] rounded font-bold shrink-0">
              [X]
            </span>
            <span>
              <strong className="text-rose-400">Morto:</strong> Falha dura comprovada (404 Not Found, recusa de conexão ou 3 falhas consecutivas de teste).
            </span>
          </li>
        </ul>
      </div>
    </div>
  );
};
