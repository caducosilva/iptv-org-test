import React, { useMemo, useRef, useState, useEffect, useCallback } from 'react';
import { Channel } from '../types';
import { Star, CheckCircle2, HelpCircle, XCircle, Tv, Radio, Cast, Monitor } from 'lucide-react';
import {
  categoriasDoCanal,
  rotuloDaCategoria,
  siglaDoPais,
  nomeDoPais,
  paisDoCanal,
  paisesDoCanal,
} from '../lib/catalog';

interface ChannelListProps {
  channels: Channel[];
  selectedChannel: Channel | null;
  onSelectChannel: (channel: Channel) => void;
  castChannel: Channel | null;
  onSelectCastChannel: (channel: Channel) => void;
  isCastPending?: boolean;
  isLoading: boolean;
  favorites: string[];
  onToggleFavorite: (channel: Channel) => void;
  isFavoritesFilter?: boolean;
  /** mostrado no estado vazio quando ha filtro de pais/categoria ativo */
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
}

/**
 * Altura fixa de cada linha. E o que permite virtualizar a lista:
 * so as linhas visiveis vao para o DOM. Antes, 5000 linhas eram
 * renderizadas de uma vez e a interface travava a cada scroll/re-render.
 */
const ROW_HEIGHT = 58;
const OVERSCAN = 8;

/** Muitas listas M3U trazem group-title="Undefined"/"N/A"; nao vale mostrar. */
export function grupoValido(group?: string): string | null {
  const g = (group || '').trim();
  if (!g) return null;
  if (['undefined', 'null', 'n/a', 'na', '-', 'sem grupo'].includes(g.toLowerCase())) return null;
  return g;
}

/** logo do canal (tvg-logo). Se a imagem falhar, mostra as iniciais. */
const ChannelLogo: React.FC<{ channel: Channel }> = ({ channel }) => {
  const [falhou, setFalhou] = useState(false);
  const iniciais = channel.name.replace(/[^\p{L}\p{N} ]/gu, '').trim().slice(0, 2).toUpperCase();

  if (!channel.logo || falhou) {
    return (
      <div className="w-8 h-8 rounded bg-slate-900 border border-slate-800 flex items-center justify-center shrink-0">
        <span className="text-[9px] font-bold text-slate-500 font-mono">{iniciais || '??'}</span>
      </div>
    );
  }

  return (
    <img
      src={channel.logo}
      alt=""
      loading="lazy"
      onError={() => setFalhou(true)}
      className="w-8 h-8 rounded object-contain bg-slate-900 border border-slate-800 shrink-0"
    />
  );
};

interface RowProps {
  channel: Channel;
  top: number;
  isAppSelected: boolean;
  isTvSelected: boolean;
  isFav: boolean;
  isCastPending: boolean;
  onSelectChannel: (c: Channel) => void;
  onSelectCastChannel: (c: Channel) => void;
  onToggleFavorite: (c: Channel) => void;
}

const ChannelRow = React.memo<RowProps>(
  ({
    channel,
    top,
    isAppSelected,
    isTvSelected,
    isFav,
    isCastPending,
    onSelectChannel,
    onSelectCastChannel,
    onToggleFavorite,
  }) => {
    const isConfirmed = channel.confirmed || channel.health === 'confirmed';
    // no maximo 2 categorias por linha: mais que isso empurra o nome do canal
    const categorias = categoriasDoCanal(channel).slice(0, 2);
    const signal =
      channel.signalStrength ??
      channel.score ??
      (channel.health === 'ok' ? 85 : channel.health === 'doubt' ? 25 : 0);
    const isDead = channel.health === 'dead';

    return (
      <div
        style={{ top, height: ROW_HEIGHT }}
        onClick={() => onSelectChannel(channel)}
        className={`absolute left-0 right-0 px-3 flex items-center justify-between gap-2.5 cursor-pointer select-none border-b border-slate-800/60 transition-colors duration-75 ${
          isAppSelected
            ? 'bg-indigo-950/80 border-l-4 border-l-indigo-500 text-white'
            : isTvSelected
            ? 'bg-emerald-950/60 border-l-4 border-l-emerald-500 text-white'
            : isDead
            ? 'bg-slate-950/40 hover:bg-slate-900/60 opacity-60 border-l-4 border-l-transparent'
            : 'hover:bg-slate-900/80 text-slate-200 border-l-4 border-l-transparent'
        }`}
      >
        {/* Esquerda: favorito, selo de saude e nome */}
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleFavorite(channel);
            }}
            className="p-1 rounded hover:bg-slate-800 active:scale-90 transition-transform duration-100 shrink-0"
            title={isFav ? 'Remover dos Favoritos' : 'Adicionar aos Favoritos'}
          >
            <Star
              className={`w-4 h-4 ${
                isFav ? 'text-amber-400 fill-amber-400' : 'text-slate-600 hover:text-amber-400'
              }`}
            />
          </button>

          <div className="shrink-0 flex items-center gap-1">
            {isAppSelected && (
              <span
                className="px-1.5 py-0.5 rounded bg-indigo-600 text-white text-[9px] font-mono font-bold flex items-center gap-0.5"
                title="Exibindo no player do App"
              >
                <Monitor className="w-2.5 h-2.5" />
                APP
              </span>
            )}

            {isTvSelected && (
              <span
                className={`px-1.5 py-0.5 rounded bg-emerald-600 text-white text-[9px] font-mono font-bold flex items-center gap-0.5 ${
                  isCastPending ? 'animate-pulse' : ''
                }`}
                title="Canal destinado a Smart TV"
              >
                <Tv className="w-2.5 h-2.5" />
                TV
              </span>
            )}

            {isConfirmed ? (
              <span
                className="px-1.5 py-0.5 rounded bg-amber-950/60 border border-amber-800 text-amber-300 text-[10px] font-mono font-bold flex items-center gap-1"
                title="Confirmado (ja espelhou na TV)"
              >
                <Star className="w-3 h-3 text-amber-400 fill-amber-400/30" />
                [OK*]
              </span>
            ) : channel.health === 'ok' ? (
              <span
                className="px-1.5 py-0.5 rounded bg-emerald-950/60 border border-emerald-800 text-emerald-400 text-[10px] font-mono font-bold flex items-center gap-1"
                title="Canal Online (OK)"
              >
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                [OK]
              </span>
            ) : channel.health === 'doubt' ? (
              <span
                className="px-1.5 py-0.5 rounded bg-yellow-950/60 border border-yellow-800 text-yellow-300 text-[10px] font-mono font-bold flex items-center gap-1"
                title="Duvida (timeout / intermitente)"
              >
                <HelpCircle className="w-3 h-3 text-yellow-400" />
                [?]
              </span>
            ) : channel.health === 'dead' ? (
              <span
                className="px-1.5 py-0.5 rounded bg-rose-950/60 border border-rose-800 text-rose-400 text-[10px] font-mono font-bold flex items-center gap-1"
                title="Morto (fim da fila)"
              >
                <XCircle className="w-3 h-3 text-rose-400" />
                [X]
              </span>
            ) : (
              <span
                className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-400 text-[10px] font-mono font-bold flex items-center gap-1"
                title="Nao testado"
              >
                <HelpCircle className="w-3 h-3 text-slate-500" />
                [--]
              </span>
            )}
          </div>

          <ChannelLogo channel={channel} />

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className={`text-xs font-semibold truncate ${
                  isAppSelected
                    ? 'text-indigo-200'
                    : isTvSelected
                    ? 'text-emerald-200 font-bold'
                    : isDead
                    ? 'text-slate-400 line-through decoration-rose-500/50'
                    : 'text-slate-200'
                }`}
              >
                {channel.name}
              </span>
            </div>

            <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mt-0.5 truncate">
              <span
                className="font-mono text-[9px] font-bold px-1 rounded bg-slate-900 border border-slate-800 text-indigo-300/90 shrink-0"
                title={paisesDoCanal(channel).map(nomeDoPais).join(' • ')}
              >
                {siglaDoPais(paisDoCanal(channel))}
              </span>
              {categorias.map((chave) => (
                <span
                  key={chave}
                  className="px-1.5 rounded bg-slate-900 border border-slate-800 text-slate-400 text-[10px] shrink-0"
                >
                  {rotuloDaCategoria(chave)}
                </span>
              ))}
              {channel.codecs && channel.codecs.length > 0 && (
                <span className="text-indigo-300/80 font-mono hidden md:inline">
                  • {channel.codecs.join('/')}
                </span>
              )}
              {channel.health_error && (
                <span className="text-rose-400/90 font-mono truncate">• {channel.health_error}</span>
              )}
            </div>
          </div>
        </div>

        {/* Direita: sinal e botao de enviar para TV */}
        <div className="shrink-0 flex items-center gap-2 font-mono text-[11px]">
          <div
            className={`hidden sm:flex items-center gap-1 px-2 py-0.5 rounded border ${
              signal >= 70
                ? 'bg-emerald-950/50 border-emerald-800/80 text-emerald-300'
                : signal >= 30
                ? 'bg-yellow-950/50 border-yellow-800/80 text-yellow-300'
                : 'bg-rose-950/50 border-rose-800/80 text-rose-400'
            }`}
            title={`Força do sinal: ${signal}%`}
          >
            <Radio className="w-3 h-3" />
            <span className="font-bold text-[10px]">{signal}%</span>
          </div>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onSelectCastChannel(channel);
            }}
            className={`px-2 py-1.5 rounded text-[10px] font-bold flex items-center gap-1 border transition-transform duration-100 active:scale-90 ${
              isTvSelected
                ? 'bg-emerald-600 text-white border-emerald-400'
                : 'bg-slate-800 hover:bg-emerald-700/80 text-slate-300 hover:text-white border-slate-700 hover:border-emerald-500'
            }`}
            title="Espelhar este canal na TV agora"
          >
            <Cast className="w-3 h-3" />
            <span className="hidden sm:inline">Enviar TV</span>
          </button>
        </div>
      </div>
    );
  }
);
ChannelRow.displayName = 'ChannelRow';

export const ChannelList: React.FC<ChannelListProps> = ({
  channels,
  selectedChannel,
  onSelectChannel,
  castChannel,
  onSelectCastChannel,
  isCastPending = false,
  isLoading,
  favorites,
  onToggleFavorite,
  isFavoritesFilter,
  hasActiveFilters,
  onClearFilters,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(600);
  const rafRef = useRef<number | null>(null);

  // Ordena: sinal forte primeiro, mortos no fim
  const sortedChannels = useMemo(() => {
    return [...channels].sort((a, b) => {
      const isADead = a.health === 'dead';
      const isBDead = b.health === 'dead';
      if (isADead && !isBDead) return 1;
      if (!isADead && isBDead) return -1;
      const sigA = a.signalStrength ?? a.score ?? 50;
      const sigB = b.signalStrength ?? b.score ?? 50;
      return sigB - sigA;
    });
  }, [channels]);

  // Busca rapida de favoritos (antes era includes() em array por linha)
  const favoriteSet = useMemo(() => new Set(favorites), [favorites]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => setViewportHeight(el.clientHeight || 600);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Volta ao topo quando a lista muda (troca de playlist / busca)
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [channels]);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const top = e.currentTarget.scrollTop;
    if (rafRef.current !== null) return; // 1 atualizacao por frame
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      setScrollTop(top);
    });
  }, []);

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  if (isLoading) {
    return (
      <div className="flex-1 bg-slate-950 p-8 flex flex-col items-center justify-center text-slate-500 gap-2">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs font-mono">Carregando canais...</p>
      </div>
    );
  }

  if (sortedChannels.length === 0) {
    return (
      <div className="flex-1 bg-slate-950 p-8 flex flex-col items-center justify-center text-slate-500 gap-2 text-center">
        {isFavoritesFilter ? (
          <>
            <Star className="w-10 h-10 text-amber-500/60 fill-amber-500/20" />
            <p className="text-sm font-bold text-amber-300">Nenhum canal nos Favoritos</p>
            <p className="text-xs text-slate-400 max-w-sm">
              Clique na estrela ao lado de qualquer canal para salvá-lo aqui.
            </p>
          </>
        ) : (
          <>
            <Tv className="w-8 h-8 text-slate-700" />
            <p className="text-sm font-semibold text-slate-400">Nenhum canal encontrado</p>
            <p className="text-xs text-slate-600">
              {hasActiveFilters
                ? 'Esse país não tem canais nessa categoria.'
                : 'Ajuste a busca para encontrar canais.'}
            </p>
            {hasActiveFilters && onClearFilters && (
              <button
                onClick={onClearFilters}
                className="mt-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded border border-indigo-500 transition"
              >
                Limpar filtros de país e categoria
              </button>
            )}
          </>
        )}
      </div>
    );
  }

  const total = sortedChannels.length;
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const endIndex = Math.min(total, Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + OVERSCAN);
  const visible = sortedChannels.slice(startIndex, endIndex);

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex-1 min-h-0 bg-slate-950 overflow-y-auto font-sans"
    >
      {/* Espacador com a altura total: mantem a barra de rolagem correta */}
      <div style={{ height: total * ROW_HEIGHT, position: 'relative' }}>
        {visible.map((channel, i) => {
          const index = startIndex + i;
          const key = `${channel.name}|||${channel.url}`;
          return (
            <ChannelRow
              key={key}
              channel={channel}
              top={index * ROW_HEIGHT}
              isAppSelected={
                selectedChannel?.url === channel.url && selectedChannel?.name === channel.name
              }
              isTvSelected={castChannel?.url === channel.url && castChannel?.name === channel.name}
              isFav={favoriteSet.has(key) || favoriteSet.has(channel.url)}
              isCastPending={isCastPending}
              onSelectChannel={onSelectChannel}
              onSelectCastChannel={onSelectCastChannel}
              onToggleFavorite={onToggleFavorite}
            />
          );
        })}
      </div>
    </div>
  );
};
