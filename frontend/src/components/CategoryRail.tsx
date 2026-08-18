import React from 'react';
import {
  LayoutGrid,
  Tv,
  Film,
  Clapperboard,
  Baby,
  Sparkles,
  Newspaper,
  Trophy,
  Music,
  BookOpen,
  PartyPopper,
  Church,
  Landmark,
  Briefcase,
  GraduationCap,
  CloudSun,
  Plane,
  Trees,
  UtensilsCrossed,
  Car,
  ShoppingBag,
  Heart,
  FlaskConical,
  Palette,
  HelpCircle,
  Laugh,
  Users,
} from 'lucide-react';
import { OpcaoFiltro, TODOS } from '../lib/catalog';

interface CategoryRailProps {
  categorias: OpcaoFiltro[];
  categoriaSelecionada: string;
  onSelecionarCategoria: (valor: string) => void;
  /** nome do pais atual, usado no cabecalho da coluna */
  contextoPais: string;
  totalNoContexto: number;
}

/** icone por categoria: ajuda a bater o olho e achar sem ler */
const ICONES: Record<string, React.ComponentType<{ className?: string }>> = {
  mogi: Landmark,
  'globos-regionais': Tv,
  'globo-capitais': Tv,
  record: Tv,
  sbt: Tv,
  band: Tv,
  abertos: Tv,
  filmes: Film,
  series: Clapperboard,
  'series-24h': Clapperboard,
  'animes-desenhos': Sparkles,
  '4k': Sparkles,
  infantil: Baby,
  animacao: Sparkles,
  noticias: Newspaper,
  esportes: Trophy,
  musica: Music,
  documentarios: BookOpen,
  entretenimento: PartyPopper,
  comedia: Laugh,
  familia: Users,
  religioso: Church,
  legislativo: Landmark,
  negocios: Briefcase,
  educacao: GraduationCap,
  ciencia: FlaskConical,
  cultura: Palette,
  clima: CloudSun,
  viagem: Plane,
  'ar-livre': Trees,
  culinaria: UtensilsCrossed,
  automotivo: Car,
  compras: ShoppingBag,
  estilo: Heart,
  'sem-categoria': HelpCircle,
};

/**
 * Coluna que fica ao lado dos paises: dentro do pais escolhido, mostra as
 * categorias (Filmes, Séries, Infantil, Notícias, Canais abertos...) uma
 * embaixo da outra, com quantos canais cada uma tem.
 */
export const CategoryRail: React.FC<CategoryRailProps> = ({
  categorias,
  categoriaSelecionada,
  onSelecionarCategoria,
  contextoPais,
  totalNoContexto,
}) => {
  return (
    <nav className="w-full lg:w-48 bg-slate-900/60 border-r border-slate-800 flex flex-col shrink-0 lg:min-h-0 max-h-[35vh] lg:max-h-none">
      <div className="px-3 pt-3 pb-2 shrink-0">
        <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
          <LayoutGrid className="w-3.5 h-3.5 text-emerald-400" />
          Categorias
        </span>
        <p className="text-[10px] text-slate-500 mt-1 truncate" title={contextoPais}>
          em <span className="text-slate-300 font-semibold">{contextoPais}</span>
        </p>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-3 space-y-0.5">
        <button
          onClick={() => onSelecionarCategoria(TODOS)}
          className={`w-full text-left px-2.5 py-2 rounded-md flex items-center justify-between gap-2 border text-xs font-semibold transition ${
            categoriaSelecionada === TODOS
              ? 'bg-emerald-600 text-white border-emerald-400'
              : 'bg-slate-950/60 text-slate-300 border-slate-800 hover:border-slate-600 hover:text-white'
          }`}
        >
          <span className="flex items-center gap-2 truncate">
            <LayoutGrid className="w-3.5 h-3.5 shrink-0" />
            Tudo
          </span>
          <span
            className={`font-mono text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
              categoriaSelecionada === TODOS ? 'bg-black/30' : 'bg-slate-900 text-slate-500'
            }`}
          >
            {totalNoContexto.toLocaleString('pt-BR')}
          </span>
        </button>

        {categorias.map((cat) => {
          const ativo = categoriaSelecionada === cat.valor;
          const Icone = ICONES[cat.valor] || LayoutGrid;
          return (
            <button
              key={cat.valor}
              onClick={() => onSelecionarCategoria(cat.valor)}
              title={`${cat.rotulo} — ${cat.total} canais`}
              className={`w-full text-left px-2.5 py-2 rounded-md flex items-center justify-between gap-2 border text-xs transition ${
                ativo
                  ? 'bg-emerald-600 text-white border-emerald-400 font-bold'
                  : 'bg-transparent text-slate-300 border-transparent hover:bg-slate-950/70 hover:border-slate-700 hover:text-white'
              }`}
            >
              <span className="flex items-center gap-2 min-w-0">
                <Icone
                  className={`w-3.5 h-3.5 shrink-0 ${ativo ? 'text-white' : 'text-emerald-400/80'}`}
                />
                <span className="truncate">{cat.rotulo}</span>
              </span>
              <span
                className={`font-mono text-[10px] shrink-0 ${ativo ? 'text-white/90' : 'text-slate-500'}`}
              >
                {cat.total.toLocaleString('pt-BR')}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
