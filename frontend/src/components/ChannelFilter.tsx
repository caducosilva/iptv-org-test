import React, { useState, useEffect } from 'react';
import { Search, EyeOff, Activity, X, Star } from 'lucide-react';

interface ChannelFilterProps {
  searchTerm: string;
  onSearchChange: (value: string) => void;
  hideDead: boolean;
  onHideDeadChange: (value: boolean) => void;
  filteredCount: number;
  totalCount: number;
  onTestVisibleChannels: () => void;
  isBatchTesting: boolean;
  isFavoritesSelected: boolean;
  onToggleFavoritesFilter: () => void;
  favoritesCount: number;
}

export const ChannelFilter: React.FC<ChannelFilterProps> = ({
  searchTerm,
  onSearchChange,
  hideDead,
  onHideDeadChange,
  filteredCount,
  totalCount,
  onTestVisibleChannels,
  isBatchTesting,
  isFavoritesSelected,
  onToggleFavoritesFilter,
  favoritesCount,
}) => {
  const [localSearch, setLocalSearch] = useState(searchTerm);

  // Debounce search term update (300ms)
  useEffect(() => {
    const handler = setTimeout(() => {
      onSearchChange(localSearch);
    }, 300);

    return () => {
      clearTimeout(handler);
    };
  }, [localSearch, onSearchChange]);

  return (
    <div className="bg-slate-900 border-b border-slate-800 p-3 flex flex-wrap items-center justify-between gap-3 text-xs font-sans">
      {/* Search Bar */}
      <div className="relative flex-1 min-w-[200px] max-w-md">
        <Search className="w-4 h-4 text-slate-500 absolute left-2.5 top-2.5 pointer-events-none" />
        <input
          type="text"
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
          placeholder="Buscar em TODAS as listas M3U (nome ou grupo)..."
          className="w-full bg-slate-950 border border-slate-700 rounded-md pl-8 pr-8 py-2 text-slate-100 text-xs focus:outline-none focus:border-indigo-500 transition"
        />
        {localSearch && (
          <button
            onClick={() => {
              setLocalSearch('');
              onSearchChange('');
            }}
            className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Filter Options & Batch Test */}
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {/* Favoritos Quick Filter Button */}
        <button
          onClick={onToggleFavoritesFilter}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-bold select-none transition border ${
            isFavoritesSelected
              ? 'bg-amber-600 text-white border-amber-500 shadow-sm'
              : 'bg-slate-950 hover:bg-slate-800 text-amber-300 border-amber-800/60'
          }`}
          title="Filtrar apenas canais favoritados"
        >
          <Star className={`w-3.5 h-3.5 ${isFavoritesSelected ? 'fill-white' : 'fill-amber-400 text-amber-400'}`} />
          <span>Favoritos</span>
          <span className="font-mono text-[10px] px-1.5 py-0.2 rounded bg-black/40 font-extrabold">
            {favoritesCount}
          </span>
        </button>

        {/* Hide Dead Checkbox */}
        <label className="flex items-center gap-2 bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-md text-slate-300 cursor-pointer hover:border-slate-700 select-none transition">
          <input
            type="checkbox"
            checked={hideDead}
            onChange={(e) => onHideDeadChange(e.target.checked)}
            className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0"
          />
          <span className="flex items-center gap-1.5 font-medium">
            <EyeOff className="w-3.5 h-3.5 text-rose-400" /> Esconder mortos
          </span>
        </label>

        {/* Counter Badge */}
        <div className="bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-md font-mono text-slate-300 flex items-center gap-1">
          <span className="text-slate-500">canais:</span>
          <span className="font-bold text-indigo-400">{filteredCount}</span>
          <span className="text-slate-600">/ {totalCount}</span>
        </div>

        {/* Test Visible Button */}
        <button
          onClick={onTestVisibleChannels}
          disabled={isBatchTesting || filteredCount === 0}
          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 text-white font-semibold rounded-md border border-indigo-500 disabled:border-slate-800 flex items-center gap-1.5 transition"
          title="Disparar probe em lote nos canais filtrados na tela (max ~80)"
        >
          <Activity className={`w-3.5 h-3.5 ${isBatchTesting ? 'animate-spin text-indigo-200' : ''}`} />
          {isBatchTesting ? 'Testando visíveis...' : 'Testar visíveis'}
        </button>
      </div>
    </div>
  );
};

