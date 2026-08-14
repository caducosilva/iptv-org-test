import React, { useMemo, useState } from 'react';
import { Globe2, Search, Star, RefreshCw, PlayCircle, X, Layers } from 'lucide-react';
import { OpcaoFiltro, TODOS, siglaDoPais, PAIS_DESCONHECIDO } from '../lib/catalog';

interface CountryRailProps {
  paises: OpcaoFiltro[];
  paisSelecionado: string;
  onSelecionarPais: (valor: string) => void;
  totalGeral: number;
  /** total do catalogo inteiro, so informativo */
  totalCatalogo: number;
  favoritosAtivos: boolean;
  onAlternarFavoritos: () => void;
  totalFavoritos: number;
  onRecarregarCatalogo: () => void;
  recarregando: boolean;
  onAtalhoGloboRj: () => void;
  pastaM3u: string;
  totalListas: number;
}

/**
 * Coluna da esquerda: escolha do PAIS.
 * Antes isso era uma fileira de chips que rolava para os lados e ficava
 * impossivel de ler. Agora e uma lista vertical, com busca, contagem por
 * pais e Brasil no topo.
 */
export const CountryRail: React.FC<CountryRailProps> = ({
  paises,
  paisSelecionado,
  onSelecionarPais,
  totalGeral,
  totalCatalogo,
  favoritosAtivos,
  onAlternarFavoritos,
  totalFavoritos,
  onRecarregarCatalogo,
  recarregando,
  onAtalhoGloboRj,
  pastaM3u,
  totalListas,
}) => {
  const [busca, setBusca] = useState('');

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return paises;
    return paises.filter(
      (p) => p.rotulo.toLowerCase().includes(q) || p.valor.toLowerCase().includes(q)
    );
  }, [paises, busca]);

  return (
    <aside className="w-full lg:w-60 bg-slate-900 border-r border-slate-800 flex flex-col shrink-0 lg:min-h-0 max-h-[45vh] lg:max-h-none">
      {/* Bloco de controles gerais do catalogo */}
      <div className="p-3 border-b border-slate-800 space-y-2 shrink-0">
        <div className="bg-indigo-950/50 border border-indigo-800/60 rounded-lg px-3 py-2">
          <div className="flex items-center gap-1.5 text-indigo-300 text-[10px] font-bold uppercase tracking-wide">
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
            Catálogo
          </div>
          <p className="text-xl font-bold text-white font-mono leading-none mt-1">
            {totalGeral.toLocaleString('pt-BR')}
          </p>
          <p className="text-[10px] text-indigo-300/70 leading-snug mt-0.5">
            canais diferentes, de {totalCatalogo.toLocaleString('pt-BR')} linhas em {totalListas}{' '}
            lista{totalListas === 1 ? '' : 's'} M3U
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={onAlternarFavoritos}
            className={`px-2 py-1.5 rounded-md font-bold flex items-center justify-center gap-1.5 border text-[11px] transition-transform duration-100 active:scale-95 ${
              favoritosAtivos
                ? 'bg-amber-600 text-white border-amber-500'
                : 'bg-amber-950/40 hover:bg-amber-900/60 text-amber-200 border-amber-800/80'
            }`}
            title="Ver somente os canais favoritados"
          >
            <Star className="w-3.5 h-3.5 text-amber-300 fill-amber-300" />
            {totalFavoritos}
          </button>

          <button
            onClick={onRecarregarCatalogo}
            disabled={recarregando}
            className="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 active:scale-95 disabled:opacity-50 text-slate-200 text-[11px] font-semibold rounded-md border border-slate-700 flex items-center justify-center gap-1.5 transition-transform duration-100"
            title="Reler os arquivos .m3u da pasta"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-indigo-400 ${recarregando ? 'animate-spin' : ''}`} />
            Listas
          </button>
        </div>

        <button
          onClick={onAtalhoGloboRj}
          className="w-full py-1.5 px-2 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.98] text-white text-[11px] font-semibold rounded border border-indigo-500 flex items-center justify-center gap-1.5 transition-transform duration-100"
        >
          <PlayCircle className="w-3.5 h-3.5" />
          Globo Rio de Janeiro
        </button>
      </div>

      {/* Cabecalho + busca de pais */}
      <div className="px-3 pt-2.5 pb-2 shrink-0">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
            <Globe2 className="w-3.5 h-3.5 text-indigo-400" />
            Países
          </span>
          <span className="font-mono text-[10px] text-slate-500">{paises.length}</span>
        </div>

        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2 top-2 pointer-events-none" />
          <input
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar país..."
            className="w-full bg-slate-950 border border-slate-800 rounded-md pl-7 pr-7 py-1.5 text-slate-100 text-[11px] focus:outline-none focus:border-indigo-500 transition"
          />
          {busca && (
            <button
              onClick={() => setBusca('')}
              className="absolute right-2 top-2 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Lista vertical de paises */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-3 space-y-0.5">
        <button
          onClick={() => onSelecionarPais(TODOS)}
          className={`w-full text-left px-2.5 py-2 rounded-md flex items-center justify-between gap-2 border text-xs font-semibold transition ${
            paisSelecionado === TODOS
              ? 'bg-indigo-600 text-white border-indigo-400'
              : 'bg-slate-950/60 text-slate-300 border-slate-800 hover:border-slate-600 hover:text-white'
          }`}
        >
          <span className="flex items-center gap-2 truncate">
            <Globe2 className="w-3.5 h-3.5 shrink-0" />
            Todos os países
          </span>
          <span
            className={`font-mono text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
              paisSelecionado === TODOS ? 'bg-black/30' : 'bg-slate-900 text-slate-500'
            }`}
          >
            {totalGeral.toLocaleString('pt-BR')}
          </span>
        </button>

        {filtrados.map((p) => {
          const ativo = paisSelecionado === p.valor;
          const desconhecido = p.valor === PAIS_DESCONHECIDO;
          return (
            <button
              key={p.valor}
              onClick={() => onSelecionarPais(p.valor)}
              title={p.rotulo}
              className={`w-full text-left px-2.5 py-2 rounded-md flex items-center justify-between gap-2 border text-xs transition ${
                ativo
                  ? 'bg-indigo-600 text-white border-indigo-400 font-bold'
                  : 'bg-transparent text-slate-300 border-transparent hover:bg-slate-950/70 hover:border-slate-700 hover:text-white'
              }`}
            >
              <span className="flex items-center gap-2 min-w-0">
                <span
                  className={`font-mono text-[9px] font-bold px-1 py-0.5 rounded border shrink-0 ${
                    ativo
                      ? 'bg-black/25 border-white/20 text-white'
                      : desconhecido
                      ? 'bg-slate-900 border-slate-800 text-slate-600'
                      : 'bg-slate-900 border-slate-700 text-indigo-300'
                  }`}
                >
                  {siglaDoPais(p.valor)}
                </span>
                <span className="truncate">{p.rotulo}</span>
              </span>
              <span
                className={`font-mono text-[10px] shrink-0 ${
                  ativo ? 'text-white/90' : 'text-slate-500'
                }`}
              >
                {p.total.toLocaleString('pt-BR')}
              </span>
            </button>
          );
        })}

        {filtrados.length === 0 && (
          <p className="text-[11px] text-slate-500 px-2 py-3 text-center">
            Nenhum país com esse nome.
          </p>
        )}
      </div>

      {/* Rodape */}
      <div className="px-3 py-2 border-t border-slate-800 text-[10px] text-slate-500 shrink-0">
        <div className="flex items-center justify-between gap-2">
          <span>Pasta:</span>
          <span className="font-mono text-slate-400 truncate" title={pastaM3u}>
            {pastaM3u}
          </span>
        </div>
      </div>
    </aside>
  );
};
