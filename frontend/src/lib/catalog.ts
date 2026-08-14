import { Channel } from '../types';

/** valor sentinela de "sem filtro" usado pelos dois trilhos laterais */
export const TODOS = 'TODOS';

/** codigo usado quando o canal nao diz de que pais e */
export const PAIS_DESCONHECIDO = 'zz';

/* ------------------------------------------------------------------ *
 * PAISES
 * ------------------------------------------------------------------ */

/**
 * Nomes de pais em portugues sem precisar manter uma tabela de 250 linhas:
 * o proprio Chrome traduz o codigo ISO. Se o navegador nao tiver a API,
 * cai para o codigo em maiusculo (BR, US...).
 */
const nomesDeRegiao: Intl.DisplayNames | null = (() => {
  try {
    return new Intl.DisplayNames(['pt-BR'], { type: 'region' });
  } catch {
    return null;
  }
})();

/** o iptv-org usa alguns codigos que nao sao ISO-3166 oficiais */
const APELIDOS_ISO: Record<string, string> = {
  uk: 'GB',
  el: 'GR',
  tp: 'TL',
};

const cacheNomePais = new Map<string, string>();

export function nomeDoPais(codigo: string): string {
  const cod = (codigo || '').toLowerCase();
  if (!cod || cod === PAIS_DESCONHECIDO) return 'Sem país identificado';

  const emCache = cacheNomePais.get(cod);
  if (emCache) return emCache;

  const iso = (APELIDOS_ISO[cod] || cod).toUpperCase();
  let nome = iso;
  try {
    const traduzido = nomesDeRegiao?.of(iso);
    if (traduzido && traduzido !== iso) nome = traduzido;
  } catch {
    // codigo invalido: fica o proprio codigo
  }
  cacheNomePais.set(cod, nome);
  return nome;
}

/** sigla curta mostrada no cracha (BR, US, JP) */
export function siglaDoPais(codigo: string): string {
  const cod = (codigo || '').toLowerCase();
  if (!cod || cod === PAIS_DESCONHECIDO) return '??';
  return cod.toUpperCase();
}

/** paises que aparecem no topo da lista, na ordem, antes dos demais */
export const PAISES_FIXOS = ['br', 'us', 'pt', 'jp', 'ar'];

/** pais principal, usado no cracha da linha do canal */
export function paisDoCanal(canal: Channel): string {
  const c = (canal.country || '').toLowerCase().trim();
  return c || PAIS_DESCONHECIDO;
}

/**
 * Todos os paises do canal. O mesmo canal pode contar para mais de um pais
 * (canal internacional que tambem esta na lista brasileira, por exemplo).
 */
export function paisesDoCanal(canal: Channel): string[] {
  const lista = (canal.countries || [])
    .map((c) => (c || '').toLowerCase().trim())
    .filter(Boolean);
  if (lista.length > 0) return lista;
  const principal = (canal.country || '').toLowerCase().trim();
  return [principal || PAIS_DESCONHECIDO];
}

/* ------------------------------------------------------------------ *
 * CATEGORIAS
 * ------------------------------------------------------------------ */

export interface Categoria {
  chave: string;
  rotulo: string;
}

/**
 * As listas trazem group-title em ingles e, muitas vezes, com varias
 * categorias juntas ("Animation;Kids", "Movies;Series"). Aqui cada termo
 * vira uma categoria em portugues, e o canal pode pertencer a mais de uma.
 */
const TRADUCAO_CATEGORIA: Record<string, Categoria> = {
  general: { chave: 'abertos', rotulo: 'Canais abertos' },
  public: { chave: 'abertos', rotulo: 'Canais abertos' },
  local: { chave: 'abertos', rotulo: 'Canais abertos' },
  movies: { chave: 'filmes', rotulo: 'Filmes' },
  series: { chave: 'series', rotulo: 'Séries' },
  kids: { chave: 'infantil', rotulo: 'Infantil' },
  animation: { chave: 'animacao', rotulo: 'Animação' },
  news: { chave: 'noticias', rotulo: 'Notícias' },
  sports: { chave: 'esportes', rotulo: 'Esportes' },
  music: { chave: 'musica', rotulo: 'Música' },
  documentary: { chave: 'documentarios', rotulo: 'Documentários' },
  entertainment: { chave: 'entretenimento', rotulo: 'Entretenimento' },
  comedy: { chave: 'comedia', rotulo: 'Comédia' },
  family: { chave: 'familia', rotulo: 'Família' },
  culture: { chave: 'cultura', rotulo: 'Cultura' },
  education: { chave: 'educacao', rotulo: 'Educação' },
  science: { chave: 'ciencia', rotulo: 'Ciência' },
  religious: { chave: 'religioso', rotulo: 'Religioso' },
  business: { chave: 'negocios', rotulo: 'Negócios' },
  legislative: { chave: 'legislativo', rotulo: 'Legislativo' },
  weather: { chave: 'clima', rotulo: 'Clima' },
  travel: { chave: 'viagem', rotulo: 'Viagem' },
  outdoor: { chave: 'ar-livre', rotulo: 'Ar livre' },
  lifestyle: { chave: 'estilo', rotulo: 'Estilo de vida' },
  cooking: { chave: 'culinaria', rotulo: 'Culinária' },
  auto: { chave: 'automotivo', rotulo: 'Automotivo' },
  classic: { chave: 'classicos', rotulo: 'Clássicos' },
  shop: { chave: 'compras', rotulo: 'Compras' },
  relax: { chave: 'relax', rotulo: 'Relax' },
  animal: { chave: 'natureza', rotulo: 'Natureza' },
  nature: { chave: 'natureza', rotulo: 'Natureza' },
  xxx: { chave: 'adulto', rotulo: 'Adulto' },
};

/** listas em portugues tambem aparecem; alguns rotulos comuns */
const TRADUCAO_EXTRA: Record<string, Categoria> = {
  filmes: { chave: 'filmes', rotulo: 'Filmes' },
  cinema: { chave: 'filmes', rotulo: 'Filmes' },
  'series': { chave: 'series', rotulo: 'Séries' },
  novelas: { chave: 'series', rotulo: 'Séries' },
  infantil: { chave: 'infantil', rotulo: 'Infantil' },
  desenhos: { chave: 'infantil', rotulo: 'Infantil' },
  noticias: { chave: 'noticias', rotulo: 'Notícias' },
  jornalismo: { chave: 'noticias', rotulo: 'Notícias' },
  esportes: { chave: 'esportes', rotulo: 'Esportes' },
  futebol: { chave: 'esportes', rotulo: 'Esportes' },
  musicas: { chave: 'musica', rotulo: 'Música' },
  religiosos: { chave: 'religioso', rotulo: 'Religioso' },
  variedades: { chave: 'entretenimento', rotulo: 'Entretenimento' },
  'tv aberta': { chave: 'abertos', rotulo: 'Canais abertos' },
  'canal aberto': { chave: 'abertos', rotulo: 'Canais abertos' },
  'canais abertos': { chave: 'abertos', rotulo: 'Canais abertos' },
};

export const SEM_CATEGORIA: Categoria = { chave: 'sem-categoria', rotulo: 'Sem categoria' };

/** ordem preferida no trilho lateral; o resto vem depois, por quantidade */
export const ORDEM_CATEGORIAS = [
  'abertos',
  'filmes',
  'series',
  'infantil',
  'animacao',
  'noticias',
  'esportes',
  'documentarios',
  'musica',
  'entretenimento',
];

const rotulosPorChave = new Map<string, string>([[SEM_CATEGORIA.chave, SEM_CATEGORIA.rotulo]]);
for (const cat of [...Object.values(TRADUCAO_CATEGORIA), ...Object.values(TRADUCAO_EXTRA)]) {
  rotulosPorChave.set(cat.chave, cat.rotulo);
}

export function rotuloDaCategoria(chave: string): string {
  return rotulosPorChave.get(chave) || chave;
}

const VAZIOS = new Set(['', 'undefined', 'null', 'n/a', 'na', '-', 'outros', 'other', 'sem grupo']);

/**
 * Cache por group-title: o catalogo tem ~13 mil canais mas menos de 200
 * valores distintos de grupo, entao normalizar uma vez cada e suficiente.
 */
const cacheCategorias = new Map<string, string[]>();

function normalizarGrupo(grupo: string): string[] {
  const bruto = (grupo || '').trim();
  const emCache = cacheCategorias.get(bruto);
  if (emCache) return emCache;

  const chaves: string[] = [];
  for (const parte of bruto.split(/[;,|/]/)) {
    const termo = parte.trim().toLowerCase();
    if (!termo || VAZIOS.has(termo)) continue;
    const traduzida = TRADUCAO_CATEGORIA[termo] || TRADUCAO_EXTRA[termo];
    const chave = traduzida ? traduzida.chave : `outros:${termo}`;
    if (!traduzida && !rotulosPorChave.has(chave)) {
      // categoria desconhecida: mantem o nome original, so com inicial maiuscula
      rotulosPorChave.set(chave, parte.trim().charAt(0).toUpperCase() + parte.trim().slice(1));
    }
    if (!chaves.includes(chave)) chaves.push(chave);
  }
  const resultado = chaves.length > 0 ? chaves : [SEM_CATEGORIA.chave];
  cacheCategorias.set(bruto, resultado);
  return resultado;
}

/** categorias (uma ou mais) as quais o canal pertence */
export function categoriasDoCanal(canal: Channel): string[] {
  return normalizarGrupo(canal.group || '');
}

/* ------------------------------------------------------------------ *
 * ORDENACAO DAS OPCOES
 * ------------------------------------------------------------------ */

export interface OpcaoFiltro {
  valor: string;
  rotulo: string;
  total: number;
}

export function ordenarPaises(contagem: Map<string, number>): OpcaoFiltro[] {
  const itens = [...contagem.entries()].map(([valor, total]) => ({
    valor,
    rotulo: nomeDoPais(valor),
    total,
  }));

  return itens.sort((a, b) => {
    // desconhecido sempre por ultimo
    if (a.valor === PAIS_DESCONHECIDO) return 1;
    if (b.valor === PAIS_DESCONHECIDO) return -1;
    const fixoA = PAISES_FIXOS.indexOf(a.valor);
    const fixoB = PAISES_FIXOS.indexOf(b.valor);
    if (fixoA !== -1 || fixoB !== -1) {
      if (fixoA === -1) return 1;
      if (fixoB === -1) return -1;
      return fixoA - fixoB;
    }
    if (b.total !== a.total) return b.total - a.total;
    return a.rotulo.localeCompare(b.rotulo, 'pt-BR');
  });
}

export function ordenarCategorias(contagem: Map<string, number>): OpcaoFiltro[] {
  const itens = [...contagem.entries()].map(([valor, total]) => ({
    valor,
    rotulo: rotuloDaCategoria(valor),
    total,
  }));

  return itens.sort((a, b) => {
    if (a.valor === SEM_CATEGORIA.chave) return 1;
    if (b.valor === SEM_CATEGORIA.chave) return -1;
    const fixoA = ORDEM_CATEGORIAS.indexOf(a.valor);
    const fixoB = ORDEM_CATEGORIAS.indexOf(b.valor);
    if (fixoA !== -1 || fixoB !== -1) {
      if (fixoA === -1) return 1;
      if (fixoB === -1) return -1;
      return fixoA - fixoB;
    }
    if (b.total !== a.total) return b.total - a.total;
    return a.rotulo.localeCompare(b.rotulo, 'pt-BR');
  });
}
