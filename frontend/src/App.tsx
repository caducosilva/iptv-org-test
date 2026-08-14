import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  HealthResponse,
  ProbeStatusResponse,
  Playlist,
  Channel,
  Device,
  PreviewResponse,
  CastStatusResponse,
  LogEntry,
  ToastNotification,
} from './types';
import { api } from './services/api';
import { Header } from './components/Header';
import { CountryRail } from './components/CountryRail';
import { CategoryRail } from './components/CategoryRail';
import { ChannelFilter } from './components/ChannelFilter';
import { ChannelList } from './components/ChannelList';
import { PreviewPanel } from './components/PreviewPanel';
import { DeviceAndCast } from './components/DeviceAndCast';
import { LiveLog } from './components/LiveLog';
import { HealthPanel } from './components/HealthPanel';
import { ToastContainer } from './components/ToastContainer';
import {
  TODOS,
  paisesDoCanal,
  categoriasDoCanal,
  nomeDoPais,
  siglaDoPais,
  rotuloDaCategoria,
  ordenarPaises,
  ordenarCategorias,
} from './lib/catalog';
import { AlertCircle, X, Globe2, LayoutGrid } from 'lucide-react';

export default function App() {
  // State
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [probeStatus, setProbeStatus] = useState<ProbeStatusResponse | null>(null);
  const [apiConnected, setApiConnected] = useState<boolean>(true);
  const [folderPath, setFolderPath] = useState<string>('D:\\IPTV');
  const [catalogVersion, setCatalogVersion] = useState<number>(0);

  // Toasts / Popups
  const [toasts, setToasts] = useState<ToastNotification[]>([]);

  const addToast = useCallback((title: string, message: string, type: ToastNotification['type'] = 'fallback') => {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: ToastNotification = { id, title, message, type };
    setToasts((prev) => [...prev, newToast]);

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Playlists (so informativo) e canais
  // Nao existe mais filtro por lista M3U: todos os canais ficam num lugar so
  // e a busca varre o catalogo inteiro.
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [favoritesOnly, setFavoritesOnly] = useState<boolean>(false);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [totalChannelsCount, setTotalChannelsCount] = useState<number>(0);
  /** total do catalogo inteiro, independente da busca (vem do /catalog) */
  const [catalogTotal, setCatalogTotal] = useState<number>(0);
  const [isLoadingChannels, setIsLoadingChannels] = useState<boolean>(false);
  const [isReloadingCatalog, setIsReloadingCatalog] = useState<boolean>(false);

  // Filters
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [hideDead, setHideDead] = useState<boolean>(false);
  /** pais = codigo ISO vindo do tvg-id; categoria = group-title normalizado */
  const [selectedCountry, setSelectedCountry] = useState<string>(TODOS);
  const [selectedCategory, setSelectedCategory] = useState<string>(TODOS);

  // Favorites
  const [favorites, setFavorites] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('iptv_companion_favorites');
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      return [];
    }
  });

  const handleToggleFavorite = useCallback(
    (channel: Channel) => {
      const key = `${channel.name}|||${channel.url}`;
      setFavorites((prev) => {
        const exists = prev.includes(key) || prev.includes(channel.url);
        let updated: string[];
        if (exists) {
          updated = prev.filter((k) => k !== key && k !== channel.url);
          addToast('Removido dos Favoritos', `Canal "${channel.name}" foi removido dos seus favoritos.`, 'info');
        } else {
          updated = [...prev, key];
          addToast('Salvo nos Favoritos ⭐', `Canal "${channel.name}" adicionado com sucesso aos favoritos!`, 'info');
        }
        try {
          localStorage.setItem('iptv_companion_favorites', JSON.stringify(updated));
        } catch (e) {
          // ignore
        }
        return updated;
      });
    },
    [addToast]
  );

  // Selection & Preview
  const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);

  // Independent TV Cast Channel
  const [castChannel, setCastChannel] = useState<Channel | null>(null);

  // Devices & Cast
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [isScanningDevices, setIsScanningDevices] = useState<boolean>(false);
  const [isCastPending, setIsCastPending] = useState<boolean>(false);
  const [castStatus, setCastStatus] = useState<CastStatusResponse | null>(null);

  // Probe Batch
  const [isBatchTesting, setIsBatchTesting] = useState<boolean>(false);

  // Logs
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isRefreshingLogs, setIsRefreshingLogs] = useState<boolean>(false);

  // Connection error message box
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Helper for appending logs
  const addLog = useCallback((phase: LogEntry['phase'], message: string) => {
    const entry: LogEntry = {
      id: Math.random().toString(36).substring(2, 9),
      timestamp: new Date().toLocaleTimeString('pt-BR'),
      phase,
      message,
    };
    setLogs((prev) => [...prev.slice(-100), entry]); // Keep last 100 entries
  }, []);

  // 1. Fetch Health Status
  const fetchHealth = useCallback(async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
      setApiConnected(true);
      setConnectionError(null);
      if (h.pending) {
        setIsCastPending(true);
      }
    } catch (err: any) {
      setApiConnected(false);
      setConnectionError(
        err?.isTimeout
          ? 'O servidor local demorou demais para responder. Ele pode estar ocupado carregando as listas.'
          : 'Sem conexão com http://127.0.0.1:8769. Verifique se o IPTV Cast Companion está rodando no seu computador.'
      );
    }
  }, []);

  // 2. Fetch Devices
  const fetchDevices = useCallback(async () => {
    try {
      const res = await api.getDevices();
      const list = res.devices || [];
      setDevices(list);
      // mantem a selecao valida; prefere uma TV que respondeu agora
      setSelectedDevice((prev) => {
        if (prev && list.some((d) => d.host === prev.host)) {
          return list.find((d) => d.host === prev.host) || prev;
        }
        return list.find((d) => d.castable !== false && d.reachable) ||
          list.find((d) => d.castable !== false) ||
          null;
      });
    } catch (err) {
      // Ignore background device fetch errors
    }
  }, []);

  // 3. Scan Devices
  const handleRescanDevices = useCallback(async () => {
    setIsScanningDevices(true);
    addLog('scan', 'Procurando TVs e Chromecasts na rede local (leva ~11s)...');
    try {
      const res = await api.scanDevices();
      const list = res.devices || [];
      setDevices(list);
      const castable = list.filter((d) => d.castable !== false);
      setSelectedDevice(castable.find((d) => d.reachable) || castable[0] || null);

      if (castable.length > 0) {
        addLog('scan', `${castable.length} TV(s) encontrada(s): ${castable.map((d) => d.friendlyName).join(', ')}`);
      } else {
        addLog('scan', `Nenhuma TV compativel encontrada (${list.length} aparelho(s) na rede).`);
        addToast(
          'Nenhuma TV encontrada',
          'Ligue a TV (standby não basta), confirme o mesmo Wi-Fi e tente novamente.',
          'warning'
        );
      }
    } catch (err: any) {
      addLog('error', `Falha ao procurar TVs: ${err.message || 'Erro de conexao'}`);
      addToast('Falha na busca', err.message || 'Erro de conexão com o servidor local.', 'warning');
    } finally {
      setIsScanningDevices(false);
    }
  }, [addLog, addToast]);

  // 4. Fetch Playlists
  const fetchPlaylists = useCallback(async () => {
    try {
      const res = await api.getPlaylists();
      setPlaylists(res.playlists || []);
      setFolderPath(res.folder || 'D:\\IPTV');
      if (res.version) setCatalogVersion(res.version);
    } catch (err) {
      // Ignore
    }
  }, []);

  // 5. Fetch Channels — sempre TODAS as listas juntas (busca global)
  const fetchChannels = useCallback(async () => {
    setIsLoadingChannels(true);
    try {
      const res = await api.getChannels({
        q: searchTerm,
        // sem playlist: o backend varre o catalogo inteiro
        hide_dead: hideDead,
        limit: 30000,
      });

      let fetchedChannels = res.channels || [];
      const totalDoCatalogo = res.count || fetchedChannels.length;

      if (favoritesOnly) {
        fetchedChannels = fetchedChannels.filter((c) => {
          const key = `${c.name}|||${c.url}`;
          return favorites.includes(key) || favorites.includes(c.url);
        });
      }

      setChannels(fetchedChannels);
      setTotalChannelsCount(totalDoCatalogo);
      if (res.version) setCatalogVersion(res.version);
      if (res.folder) setFolderPath(res.folder);
      setApiConnected(true);

      if (fetchedChannels.length > 0) {
        setSelectedChannel((prev) => prev || fetchedChannels[0]);
        setCastChannel((prev) => prev || fetchedChannels[0]);
      }
    } catch (err: any) {
      setApiConnected(false);
    } finally {
      setIsLoadingChannels(false);
    }
  }, [searchTerm, hideDead, favoritesOnly, favorites]);

  // 6. Fetch Probe Status
  const fetchProbeStatus = useCallback(async () => {
    try {
      const res = await api.getProbeStatus();
      setProbeStatus(res);
      if (res.probe?.running) {
        setIsBatchTesting(true);
      } else {
        setIsBatchTesting(false);
      }
    } catch (err) {
      // Ignore background probe check
    }
  }, []);

  // 7. Reload Catalog
  const handleReloadCatalog = useCallback(async () => {
    setIsReloadingCatalog(true);
    addLog('info', 'Solicitando releitura do catalogo de listas M3U...');
    try {
      const res = await api.reloadCatalog();
      setCatalogVersion(res.version);
      setFolderPath(res.folder);
      addLog('info', `Catalogo recarregado (v${res.version}). ${res.channels} canais atualizados.`);
      await fetchPlaylists();
      await fetchChannels();
    } catch (err: any) {
      addLog('error', `Erro ao recarregar catalogo: ${err.message}`);
    } finally {
      setIsReloadingCatalog(false);
    }
  }, [addLog, fetchPlaylists, fetchChannels]);

  // 8. Fallback Channel Search Helper
  const findBestFallbackChannel = useCallback(
    (targetChannel: Channel): Channel | null => {
      const sig = targetChannel.signalStrength ?? targetChannel.score ?? (targetChannel.health === 'ok' ? 85 : 15);
      if (sig >= 30 && targetChannel.health !== 'dead') {
        return null; // Signal acceptable
      }

      const nameUpper = targetChannel.name.toUpperCase();
      const keywords = ['GLOBO', 'SPORTV', 'PREMIERE', 'ESPN', 'SBT', 'RECORD', 'BAND', 'CAZE', 'CAZÉ', 'TELECINE', 'HBO'];
      const matchedKey = keywords.find((k) => nameUpper.includes(k));

      if (!matchedKey) return null;

      const candidates = channels.filter((c) => {
        if (c.url === targetChannel.url) return false;
        if (c.health === 'dead') return false;
        const cSig = c.signalStrength ?? c.score ?? 0;
        return c.name.toUpperCase().includes(matchedKey) && cSig >= 50;
      });

      if (candidates.length === 0) return null;

      candidates.sort((a, b) => (b.signalStrength ?? b.score ?? 0) - (a.signalStrength ?? a.score ?? 0));
      return candidates[0];
    },
    [channels]
  );

  // 9. Select Channel & Trigger Preview with Auto-Fallback
  const handleSelectChannel = useCallback(
    async (channel: Channel) => {
      let targetChannel = channel;
      const fallback = findBestFallbackChannel(channel);

      if (fallback) {
        const origSig = channel.signalStrength ?? channel.score ?? 15;
        const fallSig = fallback.signalStrength ?? fallback.score ?? 90;

        addToast(
          'Fallback Automático de Canal & Codec',
          `Sinal fraco (${origSig}%) no canal "${channel.name}". Redirecionado automaticamente para "${fallback.name}" (Sinal: ${fallSig}% • Codecs ${fallback.codecs?.join('/') || 'H.264'})!`,
          'fallback'
        );
        addLog('info', `[AUTO FALLBACK] Sinal fraco em ${channel.name} (${origSig}%) -> Redirecionado para ${fallback.name} (${fallSig}%)`);
        targetChannel = fallback;
      }

      setSelectedChannel(targetChannel);
      setPreview(null);
      setIsPreviewLoading(true);
      addLog('probe', `Testando preview do canal: ${targetChannel.name}`);

      try {
        const res = await api.getPreview(targetChannel.url, targetChannel.name);
        setPreview(res);
        if (res.ok) {
          addLog('info', `PREVIEW OK [${targetChannel.name}] (${res.contentType || 'HLS'})`);
        } else {
          addLog('error', `PREVIEW OFFLINE [${targetChannel.name}]: ${res.error || 'Falha no servidor'}`);
        }
      } catch (err: any) {
        setPreview({
          ok: false,
          url: targetChannel.url,
          error: err.message || 'Erro de conexao com a API',
        });
        addLog('error', `Erro no teste de preview: ${err.message}`);
      } finally {
        setIsPreviewLoading(false);
      }
    },
    [addLog, addToast, findBestFallbackChannel]
  );

  // 10. Shortcut Globo RJ
  const handleSelectGloboRj = useCallback(() => {
    const globoChannel: Channel = {
      name: 'TV Globo Rio de Janeiro (720p)',
      url: 'http://45.190.28.50/GLOBO_HD/index.m3u8',
      playlist: 'canais_abertos',
      group: 'VARIEDADES',
      score: 99,
      signalStrength: 98,
      codecs: ['H.264', 'AAC'],
      health: 'confirmed',
      confirmed: true,
    };
    handleSelectChannel(globoChannel);
  }, [handleSelectChannel]);

  // 11. Batch Probe
  const handleTestVisibleChannels = useCallback(async () => {
    if (channels.length === 0) return;
    const channelsToProbe = channels.slice(0, 80).map((c) => ({
      url: c.url,
      name: c.name,
    }));

    setIsBatchTesting(true);
    addLog('probe', `Iniciando teste de saude em lote para ${channelsToProbe.length} canais...`);

    try {
      const res = await api.batchProbe(channelsToProbe);
      if (res.ok) {
        addLog('probe', `Probe em lote iniciado. ${res.queued} canais na fila de analise.`);
      }
    } catch (err: any) {
      addLog('error', `Falha ao iniciar batch probe: ${err.message}`);
      setIsBatchTesting(false);
    }
  }, [channels, addLog]);

  // 12. Start Cast
  // Transmite EXATAMENTE o canal pedido. A versao antiga trocava o canal
  // sozinha quando o sinal parecia fraco, entao o usuario clicava em um canal
  // e a TV recebia outro. Se falhar, sugerimos alternativa sem trocar nada.
  const handleStartCast = useCallback(
    async (device: Device, channel: Channel) => {
      setCastChannel(channel);
      setIsCastPending(true);
      setCastStatus({
        pending: true,
        ok: true,
        phase: 'queued',
        message: `Preparando o envio de "${channel.name}" para ${device.friendlyName}...`,
        error: null,
        device: device.friendlyName,
        host: device.host,
        url: channel.url,
        source_url: channel.url,
        title: channel.name,
      });

      addLog('started', `Enviando Cast: ${channel.name} -> ${device.friendlyName} (${device.host})`);

      try {
        const res = await api.cast({
          url: channel.url,
          title: channel.name,
          channelName: channel.name,
          deviceName: device.host, // Prefer IP host
          host: device.host,
          deviceLabel: `${device.friendlyName} @ ${device.host}`,
        });
        if (res && res.ok === false) {
          throw new Error(res.message || res.error || 'O servidor recusou o comando de cast.');
        }
      } catch (err: any) {
        setIsCastPending(false);
        setCastStatus({
          pending: false,
          ok: false,
          phase: 'error',
          message: err.message || 'Erro ao enviar comando de cast',
          error: err.message || 'erro desconhecido',
          device: device.friendlyName,
          host: device.host,
          url: channel.url,
          source_url: channel.url,
          title: channel.name,
        });
        addLog('error', `Falha ao transmitir: ${err.message}`);
        addToast('Falha ao espelhar', err.message || 'Erro ao falar com o servidor local.', 'warning');
      }
    },
    [addLog, addToast]
  );

  // 12b. Cancelar / parar transmissao
  const handleStopCast = useCallback(async () => {
    addLog('info', 'Cancelando transmissao para a TV...');
    try {
      await api.stopCast();
    } catch (err: any) {
      addLog('error', `Falha ao cancelar: ${err.message}`);
    } finally {
      setIsCastPending(false);
      setCastStatus((prev) =>
        prev
          ? {
              ...prev,
              pending: false,
              ok: false,
              phase: 'error',
              message: 'Transmissao cancelada.',
              error: 'cancelado pelo usuario',
            }
          : prev
      );
    }
  }, [addLog]);

  // 13. Define o canal da TV (sem transmitir)
  const handleSelectCastChannel = useCallback(
    (channel: Channel) => {
      setCastChannel(channel);
      if (!selectedDevice) {
        addToast(
          'Canal da TV definido',
          `"${channel.name}" está pronto para ir à TV. Ligue a TV e clique em "Procurar TVs".`,
          'info'
        );
      }
    },
    [selectedDevice, addToast]
  );

  // 13b. Botao "Enviar TV" da lista: define e ja transmite
  const handleCastChannelNow = useCallback(
    (channel: Channel) => {
      setCastChannel(channel);
      if (selectedDevice) {
        handleStartCast(selectedDevice, channel);
      } else {
        addToast(
          'Nenhuma TV selecionada',
          `"${channel.name}" ficou pronto para a TV. Ligue a TV e clique em "Procurar TVs".`,
          'warning'
        );
      }
    },
    [selectedDevice, addToast, handleStartCast]
  );

  // 12. Fetch Logs
  const fetchLogs = useCallback(async () => {
    setIsRefreshingLogs(true);
    try {
      const res = await api.getCastLog();
      if (res.logs && res.logs.length > 0) {
        const parsed: LogEntry[] = res.logs.map((line, index) => ({
          id: `remote-${index}-${Date.now()}`,
          timestamp: new Date().toLocaleTimeString('pt-BR'),
          phase: line.includes('error')
            ? 'error'
            : line.includes('scan')
            ? 'scan'
            : line.includes('probe')
            ? 'probe'
            : line.includes('started') || line.includes('running')
            ? 'started'
            : 'info',
          message: line,
        }));
        setLogs(parsed);
      }
    } catch (err) {
      // Ignore
    } finally {
      setIsRefreshingLogs(false);
    }
  }, []);

  // Poll catalog version (8s: a 2s o app recarregava a lista com muita frequencia)
  const prevVersionRef = useRef<number>(0);
  useEffect(() => {
    const catalogTimer = setInterval(async () => {
      try {
        const cat = await api.getCatalog();
        if (cat.channels) setCatalogTotal(cat.channels);
        if (cat.version && cat.version !== prevVersionRef.current) {
          if (prevVersionRef.current !== 0) {
            addLog('info', `Novo arquivo M3U detectado na pasta! Catalogo atualizado para v${cat.version}`);
            fetchPlaylists();
            fetchChannels();
          }
          prevVersionRef.current = cat.version;
          setCatalogVersion(cat.version);
        }
      } catch (e) {
        // Ignore
      }
    }, 8000);

    return () => clearInterval(catalogTimer);
  }, [addLog, fetchPlaylists, fetchChannels]);

  // Poll Health every 5s
  useEffect(() => {
    fetchHealth();
    const healthTimer = setInterval(fetchHealth, 5000);
    return () => clearInterval(healthTimer);
  }, [fetchHealth]);

  // Poll Probe Status every 4s
  useEffect(() => {
    fetchProbeStatus();
    const probeTimer = setInterval(fetchProbeStatus, 4000);
    return () => clearInterval(probeTimer);
  }, [fetchProbeStatus]);

  // Poll Cast Status every 1s while pending (com teto de seguranca)
  const CAST_MAX_WAIT_MS = 150000; // backend mata o worker em 120s
  useEffect(() => {
    if (!isCastPending) return;
    const startedAt = Date.now();

    const interval = setInterval(async () => {
      // Rede travada / backend mudo: nao deixa o botao girando pra sempre
      if (Date.now() - startedAt > CAST_MAX_WAIT_MS) {
        setIsCastPending(false);
        setCastStatus((prev) =>
          prev
            ? {
                ...prev,
                pending: false,
                ok: false,
                phase: 'error',
                message: 'A TV não respondeu a tempo. Verifique se ela está ligada e na mesma rede.',
                error: 'timeout',
                hint: 'tv_offline',
              }
            : prev
        );
        addLog('error', 'Espelhamento abortado: a TV nao respondeu a tempo.');
        return;
      }

      try {
        const status = await api.getCastStatus();
        setCastStatus(status);
        if (!status.pending) {
          setIsCastPending(false);
          if (status.ok && status.phase === 'success') {
            addLog('success', `Espelhamento ativo: ${status.message}`);
            addToast(
              'No ar na TV ✅',
              `${status.title || 'Canal'} está sendo espelhado em ${status.device || 'sua TV'}.`,
              'success'
            );
            fetchChannels(); // atualiza o selo de "confirmado"
          } else if (status.error || status.phase === 'error') {
            addLog('error', `Espelhamento falhou: ${status.message || status.error}`);
            addToast('Falha no espelhamento', status.message || status.error || 'Erro desconhecido', 'warning');

            // Sugere alternativa SEM trocar nada por conta propria
            const failedName = status.title || '';
            const failed = channels.find((c) => c.name === failedName);
            const alt = failed ? findBestFallbackChannel(failed) : null;
            if (alt) {
              addToast(
                'Sugestão de canal',
                `"${alt.name}" (${alt.signalStrength ?? alt.score ?? 0}% de sinal) costuma funcionar. Clique nele para tentar.`,
                'info'
              );
            }
          }
        }
      } catch (err) {
        // segue tentando ate o teto acima
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isCastPending, addLog, addToast, fetchChannels, channels, findBestFallbackChannel]);

  // Initial Load
  useEffect(() => {
    addLog('info', 'IPTV Cast Companion iniciado. Conectando a http://127.0.0.1:8769');
    fetchHealth();
    fetchDevices();
    fetchPlaylists();
    fetchChannels();
    api
      .getCatalog()
      .then((cat) => {
        if (cat.channels) setCatalogTotal(cat.channels);
      })
      .catch(() => undefined);
  }, [addLog, fetchHealth, fetchDevices, fetchPlaylists, fetchChannels]);

  // NOTA: aqui existia um timer que, a cada 15s, reescrevia o array inteiro de
  // canais com uma variacao ALEATORIA de sinal. Isso (a) inventava numeros que
  // nao vinham do backend e (b) recriava 5000 objetos, forcando o React a
  // re-renderizar a lista toda - era a causa principal da interface travando.
  // O sinal real vem do /channels e do /probe/status.

  // Uma unica passada pelo catalogo calcula: quantos canais cada pais tem
  // (respeitando a categoria escolhida), quantos canais cada categoria tem
  // (respeitando o pais escolhido) e a lista final ja filtrada.
  const { countryOptions, categoryOptions, visibleChannels, countryTotal } = useMemo(() => {
    const porPais = new Map<string, number>();
    const porCategoria = new Map<string, number>();
    const visiveis: Channel[] = [];
    let totalDoPais = 0;

    for (const canal of channels) {
      const paises = paisesDoCanal(canal);
      const categorias = categoriasDoCanal(canal);
      const casaPais = selectedCountry === TODOS || paises.includes(selectedCountry);
      const casaCategoria = selectedCategory === TODOS || categorias.includes(selectedCategory);

      if (casaCategoria) {
        for (const pais of paises) porPais.set(pais, (porPais.get(pais) || 0) + 1);
      }
      if (casaPais) {
        totalDoPais += 1;
        for (const chave of categorias) {
          porCategoria.set(chave, (porCategoria.get(chave) || 0) + 1);
        }
      }
      if (casaPais && casaCategoria) visiveis.push(canal);
    }

    const paises = ordenarPaises(porPais);
    const categorias = ordenarCategorias(porCategoria);

    // mantem visivel a categoria escolhida mesmo que o pais atual nao tenha
    // nenhum canal dela; senao o item sumiria do trilho e o usuario ficaria
    // com a lista vazia sem entender por que.
    if (selectedCategory !== TODOS && !categorias.some((c) => c.valor === selectedCategory)) {
      categorias.push({ valor: selectedCategory, rotulo: rotuloDaCategoria(selectedCategory), total: 0 });
    }
    if (selectedCountry !== TODOS && !paises.some((p) => p.valor === selectedCountry)) {
      paises.push({ valor: selectedCountry, rotulo: nomeDoPais(selectedCountry), total: 0 });
    }

    return {
      countryOptions: paises,
      categoryOptions: categorias,
      visibleChannels: visiveis,
      countryTotal: totalDoPais,
    };
  }, [channels, selectedCountry, selectedCategory]);

  const limparFiltros = useCallback(() => {
    setSelectedCountry(TODOS);
    setSelectedCategory(TODOS);
  }, []);

  const handleRefreshAll = () => {
    fetchHealth();
    fetchDevices();
    fetchPlaylists();
    fetchChannels();
    fetchProbeStatus();
    addLog('info', 'Atualizacao geral disparada manualmente.');
  };

  // Layout: h-screen + overflow-hidden no desktop. Sem isso os filhos flex crescem
  // ate a altura total da lista (5000 canais = ~290.000px de pagina) e o navegador
  // engasga - era uma das causas do travamento.
  return (
    <div className="min-h-screen lg:h-screen lg:overflow-hidden bg-slate-950 text-slate-100 font-sans flex flex-col antialiased selection:bg-indigo-500 selection:text-white relative">
      {/* Auto-fading Popups & Toast Notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      {/* 1. Header with Health Counters and Probe Progress */}
      <Header
        health={health}
        probeStatus={probeStatus}
        apiConnected={apiConnected}
        catalogVersion={catalogVersion}
        folderPath={folderPath}
        onRefreshAll={handleRefreshAll}
      />

      {/* Connection Notice Banner if offline */}
      {connectionError && !api.getIsMockMode() && (
        <div className="bg-amber-950/80 border-b border-amber-800 text-amber-200 px-4 py-2 text-xs flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>{connectionError}</span>
          </div>
          <button
            onClick={() => {
              api.setMockMode(true);
              handleRefreshAll();
            }}
            className="px-2.5 py-1 bg-amber-600 hover:bg-amber-500 text-white font-semibold rounded text-xs transition shrink-0"
          >
            Ativar Modo de Simulação
          </button>
        </div>
      )}

      {/* Main App Layout — min-h-0 permite que os filhos rolem em vez de esticar a pagina */}
      <div className="flex-1 min-h-0 max-w-[1700px] w-full mx-auto flex flex-col lg:flex-row lg:overflow-hidden">
        {/* Coluna 1: paises (vertical, com busca) */}
        <CountryRail
          paises={countryOptions}
          paisSelecionado={selectedCountry}
          onSelecionarPais={setSelectedCountry}
          totalGeral={channels.length}
          totalCatalogo={catalogTotal || totalChannelsCount}
          favoritosAtivos={favoritesOnly}
          onAlternarFavoritos={() => setFavoritesOnly((v) => !v)}
          totalFavoritos={favorites.length}
          onRecarregarCatalogo={handleReloadCatalog}
          recarregando={isReloadingCatalog}
          onAtalhoGloboRj={handleSelectGloboRj}
          pastaM3u={folderPath}
          totalListas={playlists.length}
        />

        {/* Coluna 2: categorias dentro do pais escolhido */}
        <CategoryRail
          categorias={categoryOptions}
          categoriaSelecionada={selectedCategory}
          onSelecionarCategoria={setSelectedCategory}
          contextoPais={selectedCountry === TODOS ? 'todos os países' : nomeDoPais(selectedCountry)}
          totalNoContexto={countryTotal}
        />

        {/* Center Panel: Channel Search & Channel List */}
        <main className="flex-1 flex flex-col min-w-0 min-h-0 border-r border-slate-800 bg-slate-950">
          <ChannelFilter
            searchTerm={searchTerm}
            onSearchChange={setSearchTerm}
            hideDead={hideDead}
            onHideDeadChange={setHideDead}
            filteredCount={visibleChannels.length}
            totalCount={totalChannelsCount}
            onTestVisibleChannels={handleTestVisibleChannels}
            isBatchTesting={isBatchTesting}
            isFavoritesSelected={favoritesOnly}
            onToggleFavoritesFilter={() => setFavoritesOnly((v) => !v)}
            favoritesCount={favorites.length}
          />

          {/* Trilha do filtro atual: País › Categoria */}
          {(selectedCountry !== TODOS || selectedCategory !== TODOS) && (
            <div className="bg-slate-900/70 border-b border-slate-800 px-3 py-1.5 flex items-center gap-2 text-[11px] shrink-0">
              <span className="text-slate-500 uppercase font-bold tracking-wider text-[10px] shrink-0">
                Vendo
              </span>

              {selectedCountry !== TODOS && (
                <button
                  onClick={() => setSelectedCountry(TODOS)}
                  className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-indigo-950/70 border border-indigo-700 text-indigo-200 hover:border-indigo-400 transition"
                  title="Remover o filtro de país"
                >
                  <Globe2 className="w-3 h-3" />
                  <span className="font-semibold">{nomeDoPais(selectedCountry)}</span>
                  <span className="font-mono text-[9px] text-indigo-400">
                    {siglaDoPais(selectedCountry)}
                  </span>
                  <X className="w-3 h-3 text-indigo-400" />
                </button>
              )}

              {selectedCategory !== TODOS && (
                <button
                  onClick={() => setSelectedCategory(TODOS)}
                  className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-950/70 border border-emerald-700 text-emerald-200 hover:border-emerald-400 transition"
                  title="Remover o filtro de categoria"
                >
                  <LayoutGrid className="w-3 h-3" />
                  <span className="font-semibold">{rotuloDaCategoria(selectedCategory)}</span>
                  <X className="w-3 h-3 text-emerald-400" />
                </button>
              )}

              <button
                onClick={limparFiltros}
                className="ml-auto text-slate-400 hover:text-white underline decoration-slate-700 hover:decoration-white shrink-0"
              >
                limpar filtros
              </button>
            </div>
          )}

          <ChannelList
            channels={visibleChannels}
            selectedChannel={selectedChannel}
            onSelectChannel={handleSelectChannel}
            castChannel={castChannel}
            onSelectCastChannel={handleCastChannelNow}
            isCastPending={isCastPending}
            isLoading={isLoadingChannels}
            favorites={favorites}
            onToggleFavorite={handleToggleFavorite}
            isFavoritesFilter={favoritesOnly}
            hasActiveFilters={selectedCountry !== TODOS || selectedCategory !== TODOS}
            onClearFilters={limparFiltros}
          />
        </main>

        {/* Right Panel: Preview, Cast & Logs */}
        <aside className="w-full lg:w-96 lg:min-h-0 bg-slate-900/50 p-4 space-y-4 overflow-y-auto shrink-0 border-t lg:border-t-0 border-slate-800">
          {/* Channel Preview Panel */}
          <PreviewPanel
            channel={selectedChannel}
            preview={preview}
            isLoading={isPreviewLoading}
          />

          {/* Device & Cast Panel */}
          <DeviceAndCast
            devices={devices}
            selectedDevice={selectedDevice}
            onSelectDevice={setSelectedDevice}
            onRescanDevices={handleRescanDevices}
            isScanningDevices={isScanningDevices}
            castChannel={castChannel}
            channels={channels}
            onSelectCastChannel={handleSelectCastChannel}
            onStartCast={handleStartCast}
            onStopCast={handleStopCast}
            isCastPending={isCastPending}
            castStatus={castStatus}
            appChannel={selectedChannel}
          />

          {/* Live Log Console */}
          <LiveLog
            logs={logs}
            onClearLogs={() => setLogs([])}
            onRefreshLogs={fetchLogs}
            isRefreshing={isRefreshingLogs}
          />

          {/* Health Legend & Explanations */}
          <HealthPanel counts={probeStatus?.stats?.counts || { ok: 0, doubt: 0, dead: 0, confirmed: 0, unknown: 0 }} />
        </aside>
      </div>
    </div>
  );
}
