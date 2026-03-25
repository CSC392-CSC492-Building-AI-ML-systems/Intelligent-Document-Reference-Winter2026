/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  miniMode?: {
    dismiss: () => void;
    focusMainWindow: () => void;
    openFileInMain: (filePath: string) => void;
  };
}
