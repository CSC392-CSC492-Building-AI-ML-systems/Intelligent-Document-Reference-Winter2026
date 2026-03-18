import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';

export type MessageRole = 'user' | 'assistant';

export interface Citation {
  file_path: string;
  file_name: string;
  snippet: string;
  relevance_score: number;
  chunk_index: number;
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
export type ModelType = 'gpt-4' | 'gemini-2.5' | 'claude-3' | 'llama-3';
export type ModelProvider = 'local' | 'online';

export interface FileNode {
  id: string;
  name: string;
  type: 'file' | 'folder';
  path: string;
  selected?: boolean;
  status?: 'indexed' | 'pending' | 'unsupported' | 'failed' | 'outdated';
  children?: FileNode[];
}

interface ChatContextType {
  messages: Message[];
  inferenceMode: InferenceMode;
  selectedModel: ModelType;
  selectedFiles: string[];
  fileTree: FileNode[];
  modelProvider: ModelProvider;
  localEndpoint: string;
  apiKeys: Record<string, string>;
  temperature: number;
  contextSize: number;
  indexedFiles: string[];
  indexedDirectories: string[];
  excludedFiles: string[];
  excludedDirectories: string[];
  exclusionPatterns: string[];
  isLoading: boolean;
  pipelineReady: boolean;
  indexedChunkCount: number;
  // General settings
  systemPrompt: string;
  darkMode: boolean;
  userInfo: string;
  sendMessage: (content: string) => Promise<void>;
  setInferenceMode: (mode: InferenceMode) => void;
  setSelectedModel: (model: ModelType) => void;
  toggleFileSelection: (path: string) => void;
  setModelProvider: (provider: ModelProvider) => void;
  setLocalEndpoint: (endpoint: string) => void;
  setApiKey: (model: string, key: string) => void;
  setTemperature: (temp: number) => void;
  setContextSize: (size: number) => void;
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
  setUserInfo: (info: string) => void;
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
  saveSettings: () => Promise<void>;
  saveSetting: (key: string, value: any) => Promise<void>;
  pickFolder: () => Promise<{ path: string; status: string } | null>;
  pickFiles: () => Promise<{ paths: string[]; status: string } | null>;
  openPath: (path: string) => Promise<void>;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

// Use relative URL when not set so same-origin works (e.g. app at 127.0.0.1:8000)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inferenceMode, setInferenceMode] = useState<InferenceMode>('retrieval');
  const [selectedModel, setSelectedModel] = useState<ModelType>('gpt-4');
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [modelProvider, setModelProvider] = useState<ModelProvider>('online');
  const [localEndpoint, setLocalEndpoint] = useState<string>('http://localhost:8000');
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({
    'gpt-4': '',
    'gemini-2.5': '',
    'claude-3': '',
  });
  const [temperature, setTemperature] = useState<number>(0.7);
  const [contextSize, setContextSize] = useState<number>(4096);
  const [indexedFiles, setIndexedFiles] = useState<string[]>([]);
  const [indexedDirectories, setIndexedDirectories] = useState<string[]>([]);
  const [excludedFiles, setExcludedFiles] = useState<string[]>([]);
  const [excludedDirectories, setExcludedDirectories] = useState<string[]>([]);
  const [exclusionPatterns, setExclusionPatterns] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [pipelineReady, setPipelineReady] = useState<boolean>(false);
  const [indexedChunkCount, setIndexedChunkCount] = useState<number>(0);
  const [watcherPath, setWatcherPathState] = useState<string | null>(null);
  const [userRoot, setUserRootState] = useState<string | null>(null);
  // General settings
  const [systemPrompt, setSystemPrompt] = useState<string>('You are a helpful AI assistant that provides accurate and detailed answers based on the provided context.');
  const [darkMode, setDarkMode] = useState<boolean>(false);
  const [userInfo, setUserInfo] = useState<string>('');

  // Track whether saved context files were loaded from backend (non-empty)
  const hadSavedContextRef = useRef(false);
  // Track whether initial auto-selection has been applied
  const initialSelectionDoneRef = useRef(false);
  // Check pipeline readiness from backend
  const checkPipelineStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/status`);
      if (response.ok) {
        const data = await response.json();
        setPipelineReady(data.ready ?? false);
        setIndexedChunkCount(data.indexed_chunks ?? 0);
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

  const loadSettings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/settings/`);
      if (!response.ok) return;
      const data = await response.json();
      if (data.selectedModel) setSelectedModel(data.selectedModel);
      if (data.modelProvider) setModelProvider(data.modelProvider);
      if (data.apiKeys) setApiKeys((prev) => ({ ...prev, ...data.apiKeys }));
      if (data.temperature !== undefined) setTemperature(data.temperature);
      if (data.contextSize !== undefined) setContextSize(data.contextSize);
      if (data.systemPrompt !== undefined) setSystemPrompt(data.systemPrompt);
      if (data.darkMode !== undefined) setDarkMode(data.darkMode);
      if (data.userInfo !== undefined) setUserInfo(data.userInfo);
      if (data.localEndpoint) setLocalEndpoint(data.localEndpoint);
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const saveSettings = async () => {
    try {
      await fetch(`${API_BASE_URL}/settings/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selectedModel,
          modelProvider,
          apiKeys,
          temperature,
          contextSize,
          systemPrompt,
          darkMode,
          userInfo,
          localEndpoint,
        }),
      });
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
          mode: inferenceMode,
          selected_files: selectedFiles,
          temperature,
          context_size: contextSize,
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
        localEndpoint,
        apiKeys,
        temperature,
        contextSize,
        indexedFiles,
        indexedDirectories,
        excludedFiles,
        excludedDirectories,
        exclusionPatterns,
        isLoading,
        pipelineReady,
        indexedChunkCount,
        systemPrompt,
        darkMode,
        userInfo,
        sendMessage,
        setInferenceMode,
        setSelectedModel,
        toggleFileSelection,
        setModelProvider,
        setLocalEndpoint,
        setApiKey,
        setTemperature,
        setContextSize,
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
        setUserInfo,
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
        saveSettings,
        saveSetting,
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