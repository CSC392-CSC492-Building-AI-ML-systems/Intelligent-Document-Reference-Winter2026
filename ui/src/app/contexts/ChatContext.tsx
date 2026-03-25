import { createContext, useContext, useState, useEffect, useRef, useMemo, ReactNode } from 'react';

export type MessageRole = 'user' | 'assistant';

export interface Citation {
  file_path: string;
  file_name: string;
  snippet: string;
  relevance_score: number;
  chunk_index: number;
  page_number?: number;
  section?: string;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  citations?: Citation[];
  model?: string;
  mode?: string;
  processingTimeMs?: number;
}

// Chat history removed - not focusing on that right now

export type InferenceMode = 'retrieval' | 'q&a' | 'deep-research';
export type ModelType = string;
export type ModelProvider = 'local' | 'online';
export type RuntimeBackend = 'local' | 'api' | 'gemini' | 'voyage';

export interface FileNode {
  id: string;
  name: string;
  type: 'file' | 'folder';
  path: string;
  selected?: boolean;
  status?: 'indexed' | 'pending' | 'indexing' | 'unsupported' | 'failed' | 'outdated';
  children?: FileNode[];
}

interface ChatContextType {
  messages: Message[];
  inferenceMode: InferenceMode;
  selectedModel: ModelType;
  selectedFiles: string[];
  fileTree: FileNode[];
  modelProvider: ModelProvider;
  inferenceBackend: RuntimeBackend;
  embeddingBackend: RuntimeBackend;
  localEndpoint: string;
  embeddingModel: string;
  embeddingDimension: number;
  availableInferenceModels: string[];
  availableEmbeddingModels: string[];
  availableEmbeddingDimensions: number[];
  localOllamaModels: string[];
  apiKeys: Record<string, string>;
  temperature: number;
  contextSize: number;
  topK: number;
  indexedFiles: string[];
  indexedDirectories: string[];
  excludedFiles: string[];
  excludedDirectories: string[];
  exclusionPatterns: string[];
  isLoading: boolean;
  pipelineReady: boolean;
  indexedChunkCount: number;
  reindexRequired: boolean;
  outdatedFileCount: number;
  // General settings
  systemPrompt: string;
  darkMode: boolean;
  sendMessage: (content: string) => Promise<void>;
  setInferenceMode: (mode: InferenceMode) => void;
  setSelectedModel: (model: ModelType) => void;
  toggleFileSelection: (path: string) => void;
  setModelProvider: (provider: ModelProvider) => void;
  setInferenceBackend: (backend: RuntimeBackend) => void;
  setEmbeddingBackend: (backend: RuntimeBackend) => void;
  setLocalEndpoint: (endpoint: string) => void;
  setEmbeddingModel: (model: string) => void;
  setEmbeddingDimension: (dimension: number) => void;
  setApiKey: (model: string, key: string) => void;
  setTemperature: (temp: number) => void;
  setContextSize: (size: number) => void;
  setTopK: (k: number) => void;
  toggleIndexedFile: (path: string) => void;
  toggleExcludedFile: (path: string) => void;
  addIndexedDirectory: (path: string) => void;
  removeIndexedDirectory: (path: string) => void;
  addExcludedDirectory: (path: string) => void;
  removeExcludedDirectory: (path: string) => void;
  addExclusionPattern: (pattern: string) => void;
  removeExclusionPattern: (pattern: string) => void;
  setSystemPrompt: (prompt: string) => void;
  setDarkMode: (enabled: boolean) => void;
  importFolder: (files: FileList, type: 'inclusion' | 'exclusion') => Promise<void>;
  setWatcherPath: (path: string) => Promise<boolean>;
  browseFolderForWatcher: (type?: 'inclusion' | 'exclusion') => Promise<{ path: string; status: string } | null>;
  addWatcherPath: (path: string) => Promise<boolean>;
  removeWatcherPath: (path: string) => Promise<void>;
  getActiveWatcherPaths: () => Promise<string[]>;
  syncWatcherPaths: (paths: string[]) => Promise<void>;
  watcherPath: string | null;
  loadWatcherPath: () => Promise<void>;
  userRoot: string | null;
  loadUserRoot: () => Promise<void>;
  saveFileIndexingConfig: (config: {
    inclusion?: { files?: string[]; directories?: string[] };
    exclusion?: { files?: string[]; directories?: string[]; patterns?: string[] };
    context?: { files?: string[] };
  }) => Promise<boolean>;
  getFileIndexingConfig: () => Promise<{ inclusion?: { directories?: string[] } }>;
  loadFileIndexingConfig: () => Promise<void>;
  loadFiles: () => Promise<void>;
  refreshPipelineStatus: () => Promise<void>;
  saveSettings: () => Promise<void>;
  saveSetting: (key: string, value: any) => Promise<void>;
  refreshOllamaModels: (endpoint?: string) => Promise<string[]>;
  refreshEmbeddingDimensions: (
    backend?: RuntimeBackend,
    model?: string,
    options?: { forceDefault?: boolean; forceRefresh?: boolean }
  ) => Promise<number[]>;
  pickFolder: () => Promise<{ path: string; status: string } | null>;
  pickFiles: () => Promise<{ paths: string[]; status: string } | null>;
  openPath: (path: string) => Promise<void>;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

// Use relative URL when not set so same-origin works (e.g. app at 127.0.0.1:8000)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

const DEFAULT_INFERENCE_MODELS: Record<string, string[]> = {
  local: ['llama3'],
  api: ['gpt-4o', 'gpt-4.1-mini'],
  gemini: ['gemini-2.5-flash-lite'],
};

const DEFAULT_EMBEDDING_MODELS: Record<string, string[]> = {
  local: ['nomic-embed-text'],
  api: ['text-embedding-3-small', 'text-embedding-3-large'],
  gemini: ['models/gemini-embedding-001'],
  voyage: ['voyage-multimodal-3.5'],
};

const EMBEDDING_DIMS_MIN_FETCH_INTERVAL_MS = 60_000;

const STATIC_EMBEDDING_DIMS: Record<string, { dims: number[]; defaultDimension: number }> = {
  'gemini|models/gemini-embedding-001': { dims: [3072], defaultDimension: 3072 },
  'gemini|models/text-embedding-004': { dims: [768], defaultDimension: 768 },
};

function getStaticDims(backend: string, model: string) {
  return STATIC_EMBEDDING_DIMS[`${backend}|${model}`] ?? null;
}

const LOCAL_EMBEDDING_MODEL_HINTS = [
  'embed',
  'embedding',
  'bge',
  'e5',
  'nomic',
  'jina',
  'snowflake',
  'gte',
  'mxbai',
];

const isLikelyLocalEmbeddingModel = (modelName: string): boolean => {
  const normalized = modelName.toLowerCase();
  return LOCAL_EMBEDDING_MODEL_HINTS.some((hint) => normalized.includes(hint));
};

const sameNumberArray = (a: number[], b: number[]): boolean => {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
};

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inferenceMode, setInferenceMode] = useState<InferenceMode>('retrieval');
  const [selectedModel, setSelectedModel] = useState<ModelType>('gemini-2.5-flash-lite');
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [modelProvider, setModelProviderState] = useState<ModelProvider>('online');
  const [inferenceBackend, setInferenceBackend] = useState<RuntimeBackend>('gemini');
  const [embeddingBackend, setEmbeddingBackend] = useState<RuntimeBackend>('gemini');
  const [localEndpoint, setLocalEndpoint] = useState<string>('http://localhost:11434');
  const [embeddingModel, setEmbeddingModel] = useState<string>('models/gemini-embedding-001');
  const [embeddingDimension, setEmbeddingDimension] = useState<number>(3072);
  const [availableEmbeddingDimensions, setAvailableEmbeddingDimensions] = useState<number[]>([3072]);
  const [localOllamaModels, setLocalOllamaModels] = useState<string[]>([]);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({
    openai: '',
    gemini: '',
    voyage: '',
    'gpt-4': '',
    'gemini-2.5': '',
    'claude-3': '',
  });
  const [temperature, setTemperature] = useState<number>(0.7);
  const [contextSize, setContextSize] = useState<number>(4096);
  const [topK, setTopK] = useState<number>(5);
  const [indexedFiles, setIndexedFiles] = useState<string[]>([]);
  const [indexedDirectories, setIndexedDirectories] = useState<string[]>([]);
  const [excludedFiles, setExcludedFiles] = useState<string[]>([]);
  const [excludedDirectories, setExcludedDirectories] = useState<string[]>([]);
  const [exclusionPatterns, setExclusionPatterns] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [pipelineReady, setPipelineReady] = useState<boolean>(false);
  const [indexedChunkCount, setIndexedChunkCount] = useState<number>(0);
  const [reindexRequired, setReindexRequired] = useState<boolean>(false);
  const [outdatedFileCount, setOutdatedFileCount] = useState<number>(0);
  const [watcherPath, setWatcherPathState] = useState<string | null>(null);
  const [userRoot, setUserRootState] = useState<string | null>(null);
  // General settings
  const [systemPrompt, setSystemPrompt] = useState<string>(
    "You are a professional assistant. Use the context below to answer accurately and concisely.\n" +
    "Return markdown only (headings, bullet lists, tables where helpful).\n" +
    "Do not append source markers in the answer text.\n" +
    "Do not include absolute or relative source file paths in the answer body."
  );
  const [darkMode, setDarkMode] = useState<boolean>(false);

  // Track whether saved context files were loaded from backend (non-empty)
  const hadSavedContextRef = useRef(false);
  // Track whether initial auto-selection has been applied
  const initialSelectionDoneRef = useRef(false);
  const embeddingDimsCacheRef = useRef(
    new Map<string, { dims: number[]; defaultDimension: number }>()
  );
  const embeddingDimsInFlightRef = useRef(new Map<string, Promise<number[]>>());
  const embeddingDimsLastFetchRef = useRef(new Map<string, number>());
  // Check pipeline readiness from backend
  const checkPipelineStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/status`);
      if (response.ok) {
        const data = await response.json();
        setPipelineReady(data.ready ?? false);
        setIndexedChunkCount(data.indexed_chunks ?? 0);
        setOutdatedFileCount(data.outdated_files ?? 0);
        setReindexRequired(Boolean(data.reindex_required ?? (data.outdated_files ?? 0) > 0));
      }
    } catch (error) {
      console.error('Failed to check pipeline status:', error);
      setPipelineReady(false);
    }
  };

  // Load files and context from backend on mount.
  // loadContextFiles runs first so hadSavedContextRef is set before the
  // file-tree auto-select effect triggers.
  useEffect(() => {
    const init = async () => {
      await loadContextFiles();
      await loadFiles();
    };
    init();
    loadFileIndexingConfig();
    loadWatcherPath();
    loadUserRoot();
    checkPipelineStatus();
    loadSettings();
  }, []);

  useEffect(() => {
    const applyMiniOpenFile = async (rawPath?: string | null) => {
      const filePath = String(rawPath || '').trim();
      if (!filePath) return;

      setSelectedFiles([filePath]);

      try {
        await fetch(`${API_BASE_URL}/files/indexing`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ context: { files: [filePath] } }),
        });
      } catch (error) {
        console.error('Failed to persist mini mode context file:', error);
      }

      if (window.location.pathname !== '/chat') {
        window.location.href = '/chat';
      }
    };

    const consumeFromStorage = () => {
      const pending = localStorage.getItem('miniMode.openFile');
      if (!pending) return;
      localStorage.removeItem('miniMode.openFile');
      void applyMiniOpenFile(pending);
    };

    const onMiniOpenFile = (event: Event) => {
      const custom = event as CustomEvent<string>;
      void applyMiniOpenFile(custom.detail);
    };

    consumeFromStorage();
    window.addEventListener('mini-mode-open-file', onMiniOpenFile as EventListener);
    window.addEventListener('focus', consumeFromStorage);

    return () => {
      window.removeEventListener('mini-mode-open-file', onMiniOpenFile as EventListener);
      window.removeEventListener('focus', consumeFromStorage);
    };
  }, []);

  // Auto-select all leaf files when the file tree first loads and no saved
  // context was found. Runs at most once (initial load only).
  // Unsupported files are excluded from auto-selection.
  useEffect(() => {
    if (
      fileTree.length > 0 &&
      !hadSavedContextRef.current &&
      !initialSelectionDoneRef.current
    ) {
      const collectLeaves = (nodes: FileNode[]): string[] =>
        nodes.flatMap((n) =>
          n.type === 'file'
            ? n.status === 'unsupported' ? [] : [n.path]
            : collectLeaves(n.children ?? [])
        );
      const allLeaves = collectLeaves(fileTree);
      if (allLeaves.length > 0) {
        setSelectedFiles(allLeaves);
      }
      initialSelectionDoneRef.current = true;
    }
  }, [fileTree]);

  // Periodically refresh the file tree to pick up status changes
  // (e.g. pending → indexed) while indexing is in progress.
  useEffect(() => {
    const interval = setInterval(() => {
      loadFiles();
    }, 10_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (inferenceBackend === 'local' || embeddingBackend === 'local') {
      refreshOllamaModels();
    }
  }, [inferenceBackend, embeddingBackend, localEndpoint]);

  const setModelProvider = (provider: ModelProvider) => {
    setModelProviderState(provider);
    if (provider === 'local') {
      setInferenceBackend('local');
      setEmbeddingBackend('local');
      return;
    }
    if (inferenceBackend === 'local') {
      // Default online inference to Gemini while still allowing manual override.
      setInferenceBackend('gemini');
    }
    if (embeddingBackend === 'local') {
      setEmbeddingBackend('api');
    }
  };

  useEffect(() => {
    const inferredProvider: ModelProvider =
      inferenceBackend === 'local' && embeddingBackend === 'local' ? 'local' : 'online';
    if (modelProvider !== inferredProvider) {
      setModelProviderState(inferredProvider);
    }
  }, [modelProvider, inferenceBackend, embeddingBackend]);

  const loadContextFiles = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/files/context`);
      const data = await response.json();
      if (data.files && Array.isArray(data.files)) {
        // Only set files, filter out directories
        const filesOnly = data.files.filter((path: string) => !path.endsWith('/'));
        if (filesOnly.length > 0) {
          hadSavedContextRef.current = true;
          setSelectedFiles(filesOnly);
        }
        // If filesOnly is empty, don't overwrite — let the auto-select
        // effect populate selectedFiles from the file tree instead.
      }
    } catch (error) {
      console.error('Failed to load context files:', error);
    }
  };

  const loadFileIndexingConfig = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/files/indexing`);
      const data = await response.json();
      if (data.inclusion) {
        if (data.inclusion.files) {
          setIndexedFiles(data.inclusion.files);
        }
        if (data.inclusion.directories) {
          setIndexedDirectories(data.inclusion.directories);
        }
      }
      if (data.exclusion) {
        if (data.exclusion.files) {
          setExcludedFiles(data.exclusion.files);
        }
        if (data.exclusion.directories) {
          setExcludedDirectories(data.exclusion.directories);
        }
        if (data.exclusion.patterns) {
          setExclusionPatterns(data.exclusion.patterns);
        }
      }
    } catch (error) {
      console.error('Failed to load file indexing config:', error);
    }
  };

  /** Fetch saved file indexing config from backend (does not update state). */
  const getFileIndexingConfig = async (): Promise<{
    inclusion?: { directories?: string[] };
  }> => {
    try {
      const response = await fetch(`${API_BASE_URL}/files/indexing`);
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Failed to get file indexing config:', error);
      return {};
    }
  };

  const loadWatcherPath = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/watcher/path`);
      const data = await response.json();
      const paths = data?.active_paths ?? [];
      // Assume only 1 folder: use first path if any
      setWatcherPathState(paths.length > 0 ? paths[0].path : null);
    } catch (error) {
      console.error('Failed to load watcher path:', error);
      setWatcherPathState(null);
    }
  };

  const loadUserRoot = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/watcher/user-root`);
      const data = await response.json();
      setUserRootState(data?.user_root ?? null);
    } catch (error) {
      console.error('Failed to load user root:', error);
      setUserRootState(null);
    }
  };

  const refreshOllamaModels = async (endpoint?: string): Promise<string[]> => {
    const target = (endpoint ?? localEndpoint).trim();
    if (!target) {
      setLocalOllamaModels([]);
      return [];
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/settings/ollama/models?endpoint=${encodeURIComponent(target)}`
      );
      if (!response.ok) {
        throw new Error(`Failed to query Ollama (${response.status})`);
      }
      const data = await response.json();
      const models = Array.isArray(data.models)
        ? data.models.filter((m: unknown): m is string => typeof m === 'string' && m.length > 0)
        : [];
      setLocalOllamaModels(models);
      return models;
    } catch (error) {
      console.error('Failed to refresh Ollama models:', error);
      setLocalOllamaModels([]);
      return [];
    }
  };

  const refreshEmbeddingDimensionsRef = useRef<
    (backend?: RuntimeBackend, model?: string, options?: { forceDefault?: boolean; forceRefresh?: boolean }) => Promise<number[]>
  >(async () => []);

  const refreshEmbeddingDimensions: typeof refreshEmbeddingDimensionsRef.current = async (
    backend,
    model,
    options,
  ) => refreshEmbeddingDimensionsRef.current(backend, model, options);

  refreshEmbeddingDimensionsRef.current = async (
    backend?: RuntimeBackend,
    model?: string,
    options?: { forceDefault?: boolean; forceRefresh?: boolean },
  ): Promise<number[]> => {
    const targetBackend = backend ?? embeddingBackend;
    const targetModel = (model ?? embeddingModel ?? '').trim();
    if (!targetBackend || !targetModel) {
      return [];
    }

    const forceRefresh = options?.forceRefresh === true;

    // Return static dimensions for known models without any network call.
    const staticDims = getStaticDims(targetBackend, targetModel);
    if (staticDims && !forceRefresh) {
      setAvailableEmbeddingDimensions((current) =>
        sameNumberArray(current, staticDims.dims) ? current : staticDims.dims
      );
      setEmbeddingDimension((current) => {
        if (options?.forceDefault) return staticDims.defaultDimension;
        return staticDims.dims.includes(current) ? current : staticDims.defaultDimension;
      });
      return staticDims.dims;
    }

    const params = new URLSearchParams({
      backend: targetBackend,
      model: targetModel,
    });
    if (targetBackend === 'local' && localEndpoint.trim()) {
      params.set('endpoint', localEndpoint.trim());
    }

    const cacheKey = params.toString();

    const inFlight = embeddingDimsInFlightRef.current.get(cacheKey);
    if (inFlight) {
      return inFlight;
    }

    const cached = embeddingDimsCacheRef.current.get(cacheKey);

    if (!forceRefresh && cached) {
      setAvailableEmbeddingDimensions((current) =>
        sameNumberArray(current, cached.dims) ? current : cached.dims
      );
      setEmbeddingDimension((current) => {
        if (options?.forceDefault) return cached.defaultDimension;
        return cached.dims.includes(current) ? current : cached.defaultDimension;
      });
      return cached.dims;
    }

    if (!forceRefresh) {
      const lastFetchedAt = embeddingDimsLastFetchRef.current.get(cacheKey) ?? 0;
      if (lastFetchedAt > 0 && Date.now() - lastFetchedAt < EMBEDDING_DIMS_MIN_FETCH_INTERVAL_MS) {
        return cached?.dims ?? [];
      }
    }

    const requestPromise = (async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/settings/embedding-dimensions?${params.toString()}`
        );
        if (!response.ok) {
          throw new Error(`Failed to fetch embedding dimensions (${response.status})`);
        }

        const data = await response.json();
        const dims = Array.isArray(data.dimensions)
          ? data.dimensions
              .map((d: unknown) => Number(d))
              .filter((d: number) => Number.isInteger(d) && d > 0)
          : [];

        if (dims.length === 0) {
          return [];
        }

        const defaultDimensionRaw = Number(data.default_dimension);
        const defaultDimension =
          Number.isInteger(defaultDimensionRaw) && defaultDimensionRaw > 0
            ? defaultDimensionRaw
            : dims[0];

        embeddingDimsCacheRef.current.set(cacheKey, {
          dims,
          defaultDimension,
        });
        embeddingDimsLastFetchRef.current.set(cacheKey, Date.now());

        setAvailableEmbeddingDimensions((current) =>
          sameNumberArray(current, dims) ? current : dims
        );
        setEmbeddingDimension((current) => {
          if (options?.forceDefault) return defaultDimension;
          return dims.includes(current) ? current : defaultDimension;
        });
        return dims;
      } catch (error) {
        console.error('Failed to refresh embedding dimensions:', error);
        embeddingDimsLastFetchRef.current.set(cacheKey, Date.now());
        return [];
      } finally {
        embeddingDimsInFlightRef.current.delete(cacheKey);
      }
    })();

    embeddingDimsInFlightRef.current.set(cacheKey, requestPromise);

    return requestPromise;
  };

  const localEmbeddingModels = useMemo(
    () => localOllamaModels.filter((m) => isLikelyLocalEmbeddingModel(m)),
    [localOllamaModels],
  );
  const localInferenceModels = useMemo(
    () => localOllamaModels.filter((m) => !isLikelyLocalEmbeddingModel(m)),
    [localOllamaModels],
  );

  const availableInferenceModels = useMemo(() => {
    if (inferenceBackend === 'local') {
      return localInferenceModels.length > 0
        ? localInferenceModels
        : DEFAULT_INFERENCE_MODELS.local;
    }
    return DEFAULT_INFERENCE_MODELS[inferenceBackend] ?? [selectedModel];
  }, [inferenceBackend, localInferenceModels, selectedModel]);

  const availableEmbeddingModels = useMemo(() => {
    if (embeddingBackend === 'local') {
      return localEmbeddingModels.length > 0
        ? localEmbeddingModels
        : DEFAULT_EMBEDDING_MODELS.local;
    }
    return DEFAULT_EMBEDDING_MODELS[embeddingBackend] ?? [embeddingModel];
  }, [embeddingBackend, localEmbeddingModels, embeddingModel]);

  useEffect(() => {
    if (availableInferenceModels.length > 0 && !availableInferenceModels.includes(selectedModel)) {
      setSelectedModel(availableInferenceModels[0]);
    }
  }, [availableInferenceModels, selectedModel]);

  useEffect(() => {
    if (availableEmbeddingModels.length > 0 && !availableEmbeddingModels.includes(embeddingModel)) {
      setEmbeddingModel(availableEmbeddingModels[0]);
    }
  }, [availableEmbeddingModels, embeddingModel]);

  const prevEmbeddingKeyRef = useRef('');
  useEffect(() => {
    if (!embeddingModel) return;
    if (embeddingBackend === 'local' && localEmbeddingModels.length === 0) return;
    const key = `${embeddingBackend}|${embeddingModel}|${embeddingBackend === 'local' ? localEndpoint : ''}`;
    if (key === prevEmbeddingKeyRef.current) return;
    prevEmbeddingKeyRef.current = key;

    // For statically-known models, apply dims directly without any network call.
    const staticDims = getStaticDims(embeddingBackend, embeddingModel);
    if (staticDims) {
      setAvailableEmbeddingDimensions((cur) =>
        sameNumberArray(cur, staticDims.dims) ? cur : staticDims.dims
      );
      setEmbeddingDimension((cur) =>
        staticDims.dims.includes(cur) ? cur : staticDims.defaultDimension
      );
      return;
    }

    refreshEmbeddingDimensionsRef.current(embeddingBackend, embeddingModel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [embeddingBackend, embeddingModel, localEndpoint, localEmbeddingModels.length]);

  const loadSettings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/settings/`);
      if (!response.ok) return;
      const data = await response.json();
      if (data.selectedModel) setSelectedModel(data.selectedModel);
      if (data.inference_model) setSelectedModel(data.inference_model);
      if (data.embedding_model) setEmbeddingModel(data.embedding_model);
      if (data.embedding_dimension !== undefined) {
        const parsed = Number(data.embedding_dimension);
        if (Number.isInteger(parsed) && parsed > 0) {
          setEmbeddingDimension(parsed);
        }
      }
      if (data.modelProvider) setModelProvider(data.modelProvider);
      if (data.inference_backend) {
        setInferenceBackend(data.inference_backend);
      } else if (data.modelProvider === 'local') {
        setInferenceBackend('local');
      }
      if (data.embedding_backend) {
        setEmbeddingBackend(data.embedding_backend);
      } else if (data.modelProvider === 'local') {
        setEmbeddingBackend('local');
      }
      if (data.apiKeys) setApiKeys((prev) => ({ ...prev, ...data.apiKeys }));
      if (data.temperature !== undefined) setTemperature(data.temperature);
      if (data.contextSize !== undefined) setContextSize(data.contextSize);
      if (data.top_k !== undefined) setTopK(data.top_k);
      if (data.systemPrompt !== undefined) setSystemPrompt(data.systemPrompt);
      if (data.darkMode !== undefined) setDarkMode(data.darkMode);
      if (data.localEndpoint) {
        setLocalEndpoint(data.localEndpoint);
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const saveSettings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/settings/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selectedModel,
          inference_model: selectedModel,
          embedding_model: embeddingModel,
          embedding_dimension: embeddingDimension,
          modelProvider,
          inference_backend: inferenceBackend,
          embedding_backend: embeddingBackend,
          apiKeys,
          temperature,
          contextSize,
          top_k: topK,
          systemPrompt,
          darkMode,
          localEndpoint,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        const requiresReindex = Boolean(data?.reindex_required);
        if (requiresReindex) {
          setReindexRequired(true);
        }
        await loadFiles();
        await checkPipelineStatus();
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
    }
  };

  /** Persist a single setting immediately (e.g. dark mode toggle). */
  const saveSetting = async (key: string, value: any) => {
    try {
      await fetch(`${API_BASE_URL}/settings/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });
    } catch (error) {
      console.error(`Failed to save setting ${key}:`, error);
    }
  };

  /** Open native folder picker and return the path only (no backend persistence). */
  const pickFolder = async (): Promise<{ path: string; status: string } | null> => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5 * 60 * 1000);
      const response = await fetch(`${API_BASE_URL}/watcher/pick-folder`, {
        method: 'POST',
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || response.statusText);
      }
      return { path: data.path ?? '', status: data.status ?? '' };
    } catch (error) {
      console.error('Failed to pick folder:', error);
      throw error;
    }
  };

  /** Open native file picker and return the selected paths only (no backend persistence). */
  const pickFiles = async (): Promise<{ paths: string[]; status: string } | null> => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5 * 60 * 1000);
      const response = await fetch(`${API_BASE_URL}/watcher/pick-files`, {
        method: 'POST',
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || response.statusText);
      }
      return { paths: data.paths ?? [], status: data.status ?? '' };
    } catch (error) {
      console.error('Failed to pick files:', error);
      throw error;
    }
  };

  const setWatcherPath = async (path: string) => {
    const trimmed = path.trim();
    if (!trimmed) return false;
    try {
      // Remove existing path so we only have one folder
      if (watcherPath) {
        const url = `${API_BASE_URL}/watcher/path?path=${encodeURIComponent(watcherPath)}`;
        await fetch(url, { method: 'DELETE' });
      }
      const response = await fetch(`${API_BASE_URL}/watcher/path`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: trimmed, excluded_files: [] }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || response.statusText);
      }
      await loadWatcherPath();
      return true;
    } catch (error) {
      console.error('Failed to set watcher path:', error);
      throw error;
    }
  };

  /** Open native folder picker (tkinter on backend); full path is added to inclusion or exclusion in YAML. */
  const browseFolderForWatcher = async (type: 'inclusion' | 'exclusion' = 'inclusion'): Promise<{ path: string; status: string } | null> => {
    try {
      const url = `${API_BASE_URL}/watcher/browse?type=${encodeURIComponent(type)}`;
      // Long timeout: backend blocks until user picks a folder in the native dialog
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5 * 60 * 1000);
      const response = await fetch(url, { method: 'POST', signal: controller.signal });
      clearTimeout(timeoutId);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || response.statusText);
      }
      if (type === 'inclusion') await loadWatcherPath();
      await loadFileIndexingConfig();
      return { path: data.path ?? '', status: data.status ?? '' };
    } catch (error) {
      console.error('Failed to browse folder:', error);
      throw error;
    }
  };

  /** Add a path to the watcher without removing others (for syncing all inclusion folders). */
  const addWatcherPath = async (path: string) => {
    const trimmed = path.trim();
    if (!trimmed) return false;
    try {
      const response = await fetch(`${API_BASE_URL}/watcher/path`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: trimmed, excluded_files: [] }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || response.statusText);
      }
      await loadWatcherPath();
      return true;
    } catch (error) {
      console.error('Failed to add watcher path:', error);
      throw error;
    }
  };

  /** Remove a path from the watcher (sets is_active=0 in monitor_config). */
  const removeWatcherPath = async (path: string) => {
    const trimmed = path.trim();
    if (!trimmed) return;
    try {
      const url = `${API_BASE_URL}/watcher/path?path=${encodeURIComponent(trimmed)}`;
      const response = await fetch(url, { method: 'DELETE' });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || response.statusText);
      }
      await loadWatcherPath();
    } catch (error) {
      console.error('Failed to remove watcher path:', error);
      throw error;
    }
  };

  /** Return list of currently active watcher paths (from monitor_config where is_active=1). */
  const getActiveWatcherPaths = async (): Promise<string[]> => {
    try {
      const response = await fetch(`${API_BASE_URL}/watcher/path`);
      const data = await response.json();
      const paths = data?.active_paths ?? [];
      return paths.map((p: { path?: string }) => p.path).filter(Boolean);
    } catch (error) {
      console.error('Failed to get active watcher paths:', error);
      return [];
    }
  };

  /**
   * Sync monitor_config with the inclusion list: backend sets is_active=0 for paths
   * not in the list and is_active=1 for paths in the list (normalized comparison).
   */
  const syncWatcherPaths = async (paths: string[]) => {
    try {
      const response = await fetch(`${API_BASE_URL}/watcher/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: paths ?? [] }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || response.statusText);
      }
      await loadWatcherPath();
    } catch (error) {
      console.error('Failed to sync watcher paths:', error);
      throw error;
    }
  };

  const saveFileIndexingConfig = async (config: {
    inclusion?: { files?: string[]; directories?: string[] };
    exclusion?: { files?: string[]; directories?: string[]; patterns?: string[] };
    context?: { files?: string[] };
  }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/files/indexing`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config),
      });
      const data = await response.json();
      if (data.status === 'ok') {
        // Reload context files and file tree after save
        await loadContextFiles();
        await loadFileIndexingConfig();
        await loadFiles();
        return true;
      }
      return false;
    } catch (error) {
      console.error('Failed to save file indexing config:', error);
      return false;
    }
  };

  const loadFiles = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/files/`);
      const data = await response.json();
      if (data.files && Array.isArray(data.files)) {
        setFileTree(data.files);
      }
    } catch (error) {
      console.error('Failed to load files:', error);
      // Keep empty file tree on error
      setFileTree([]);
    }
  };

  const openPath = async (path: string) => {
    const trimmed = path?.trim();
    if (!trimmed) return;
    try {
      const response = await fetch(`${API_BASE_URL}/files/open-path`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: trimmed }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `Failed to open path (${response.status})`);
      }
    } catch (error) {
      console.error('Failed to open path:', error);
      throw error;
    }
  };

  const sendMessage = async (content: string) => {
    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/chat/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: content,
          model: selectedModel,
          inference_backend: inferenceBackend,
          mode: inferenceMode,
          selected_files: selectedFiles,
          temperature,
          context_size: contextSize,
          top_k: topK,
          system_prompt: systemPrompt,
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      
      const assistantMessage: Message = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: data.answer || 'No response received',
        timestamp: new Date(),
        citations: data.citations || [],
        model: data.model,
        mode: data.mode,
        processingTimeMs: data.processing_time_ms,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Failed to send message:', error);
      const detail = error instanceof Error ? error.message : 'Unknown error';
      const errorMessage: Message = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: `Error: ${detail}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleFileSelection = (path: string) => {
    setSelectedFiles((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]
    );
  };

  const setApiKey = (model: string, key: string) => {
    setApiKeys((prev) => ({ ...prev, [model]: key }));
  };

  const toggleIndexedFile = (path: string) => {
    setIndexedFiles((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]
    );
  };

  const toggleExcludedFile = (path: string) => {
    setExcludedFiles((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]
    );
  };

  const addExclusionPattern = (pattern: string) => {
    setExclusionPatterns((prev) => [...prev, pattern]);
  };

  const removeExclusionPattern = (pattern: string) => {
    setExclusionPatterns((prev) => prev.filter((p) => p !== pattern));
  };

  const importFolder = async (files: FileList, type: 'inclusion' | 'exclusion') => {
    try {
      if (files.length === 0) return;
      
      // Extract folder path from first file's webkitRelativePath (e.g. "TEST" or "parent/TEST")
      const firstFile = files[0] as File & { webkitRelativePath?: string };
      if (!firstFile.webkitRelativePath) {
        throw new Error('Folder selection not supported in this browser');
      }
      
      const folderName = firstFile.webkitRelativePath.split('/')[0];
      const allFilePaths: string[] = [];
      
      Array.from(files).forEach((file) => {
        const fileWithPath = file as File & { webkitRelativePath?: string };
        if (fileWithPath.webkitRelativePath) {
          allFilePaths.push(fileWithPath.webkitRelativePath);
        }
      });

      // Base for full paths: watcher path if set, otherwise user home (so imports don't end up in project folder)
      const base = (watcherPath ?? userRoot ?? '').trim().replace(/\/$/, '');
      const dirToAdd = base ? `${base}/${folderName}` : folderName;
      const toFullPath = (rel: string) => (base ? `${base}/${rel}` : rel);
      
      if (type === 'inclusion') {
        if (!indexedDirectories.includes(dirToAdd)) {
          setIndexedDirectories((prev) => [...prev, dirToAdd]);
        }
        setIndexedFiles((prev) => {
          const newFiles = [...prev];
          allFilePaths.forEach((rel) => {
            const path = toFullPath(rel);
            if (!newFiles.includes(path)) newFiles.push(path);
          });
          return newFiles;
        });
      } else {
        const exclDir = base ? `${base}/${folderName}` : folderName;
        if (!excludedDirectories.includes(exclDir)) {
          setExcludedDirectories((prev) => [...prev, exclDir]);
        }
        setExcludedFiles((prev) => {
          const newFiles = [...prev];
          allFilePaths.forEach((rel) => {
            const path = toFullPath(rel);
            if (!newFiles.includes(path)) newFiles.push(path);
          });
          return newFiles;
        });
      }
    } catch (error) {
      console.error('Failed to import folder:', error);
      throw error;
    }
  };

  const addIndexedDirectory = (path: string) => {
    if (!indexedDirectories.includes(path)) {
      setIndexedDirectories((prev) => [...prev, path]);
    }
  };

  const removeIndexedDirectory = (path: string) => {
    setIndexedDirectories((prev) => prev.filter((p) => p !== path));
    // Also remove all files from that directory
    setIndexedFiles((prev) => prev.filter((p) => !p.startsWith(path)));
  };

  const addExcludedDirectory = (path: string) => {
    if (!excludedDirectories.includes(path)) {
      setExcludedDirectories((prev) => [...prev, path]);
    }
  };

  const removeExcludedDirectory = (path: string) => {
    setExcludedDirectories((prev) => prev.filter((p) => p !== path));
    // Also remove all files from that directory
    setExcludedFiles((prev) => prev.filter((p) => !p.startsWith(path)));
  };

  return (
    <ChatContext.Provider
      value={{
        messages,
        inferenceMode,
        selectedModel,
        selectedFiles,
        fileTree,
        modelProvider,
        inferenceBackend,
        embeddingBackend,
        localEndpoint,
        embeddingModel,
        embeddingDimension,
        availableInferenceModels,
        availableEmbeddingModels,
        availableEmbeddingDimensions,
        localOllamaModels,
        apiKeys,
        temperature,
        contextSize,
        topK,
        indexedFiles,
        indexedDirectories,
        excludedFiles,
        excludedDirectories,
        exclusionPatterns,
        isLoading,
        pipelineReady,
        indexedChunkCount,
        reindexRequired,
        outdatedFileCount,
        systemPrompt,
        darkMode,
        sendMessage,
        setInferenceMode,
        setSelectedModel,
        toggleFileSelection,
        setModelProvider,
        setInferenceBackend,
        setEmbeddingBackend,
        setLocalEndpoint,
        setEmbeddingModel,
        setEmbeddingDimension,
        setApiKey,
        setTemperature,
        setContextSize,
        setTopK,
        toggleIndexedFile,
        toggleExcludedFile,
        addIndexedDirectory,
        removeIndexedDirectory,
        addExcludedDirectory,
        removeExcludedDirectory,
        addExclusionPattern,
        removeExclusionPattern,
        setSystemPrompt,
        setDarkMode,
        importFolder,
        setWatcherPath,
        browseFolderForWatcher,
        addWatcherPath,
        removeWatcherPath,
        getActiveWatcherPaths,
        syncWatcherPaths,
        watcherPath,
        loadWatcherPath,
        userRoot,
        loadUserRoot,
        saveFileIndexingConfig,
        getFileIndexingConfig,
        loadFileIndexingConfig,
        loadFiles,
        refreshPipelineStatus: checkPipelineStatus,
        saveSettings,
        saveSetting,
        refreshOllamaModels,
        refreshEmbeddingDimensions,
        pickFolder,
        pickFiles,
        openPath,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }
  return context;
}