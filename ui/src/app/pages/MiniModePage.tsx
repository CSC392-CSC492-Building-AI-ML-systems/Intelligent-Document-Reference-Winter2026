import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, MessageCircle, ExternalLink } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

type MiniResult = {
  file_path: string;
  file_name: string;
  parent: string;
  snippet: string;
  score: number;
};

function looksLikeQuestion(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (!t) return false;
  if (t.includes('?')) return true;
  return /^(what|why|how|when|where|who|summarize|explain|compare|find)\b/.test(t);
}

export function MiniModePage() {
  const [input, setInput] = useState('');
  const [results, setResults] = useState<MiniResult[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [queryResponse, setQueryResponse] = useState('');
  const [queryRunning, setQueryRunning] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const cls = 'mini-mode-active';
    const root = document.getElementById('root');
    document.documentElement.classList.add(cls);
    document.body.classList.add(cls);
    root?.classList.add(cls);

    return () => {
      document.documentElement.classList.remove(cls);
      document.body.classList.remove(cls);
      root?.classList.remove(cls);
    };
  }, []);

  const showAsk = useMemo(() => looksLikeQuestion(input), [input]);

  const items = useMemo(() => {
    const base: Array<{ kind: 'file' | 'ask'; data?: MiniResult }> = results.map((r) => ({
      kind: 'file',
      data: r,
    }));
    if (showAsk && input.trim()) {
      base.push({ kind: 'ask' });
    }
    return base;
  }, [results, showAsk, input]);

  useEffect(() => {
    if (activeIndex >= items.length) {
      setActiveIndex(Math.max(0, items.length - 1));
    }
  }, [items.length, activeIndex]);

  useEffect(() => {
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }

    debounceRef.current = window.setTimeout(async () => {
      const q = input.trim();
      if (!q) {
        setResults([]);
        return;
      }
      try {
        const res = await fetch(
          `${API_BASE_URL}/mini/search?q=${encodeURIComponent(q)}&limit=6`
        );
        if (!res.ok) return;
        const payload = await res.json();
        setResults(Array.isArray(payload.results) ? payload.results : []);
      } catch {
        // Keep silent to keep mini widget feeling instant.
      }
    }, 80);

    return () => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [input]);

  async function setContextFile(filePath: string): Promise<void> {
    try {
      await fetch(`${API_BASE_URL}/files/indexing`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context: { files: [filePath] } }),
      });
    } catch {
      // Best effort only.
    }
  }

  function focusFullApp(): void {
    if (window.miniMode?.focusMainWindow) {
      window.miniMode.focusMainWindow();
      return;
    }
    window.location.href = '/chat';
  }

  async function openFileInMain(filePath: string): Promise<void> {
    await setContextFile(filePath);
    if (window.miniMode?.openFileInMain) {
      window.miniMode.openFileInMain(filePath);
      return;
    }
    window.location.href = '/chat';
  }

  async function runQuickQuery(question: string): Promise<void> {
    const q = question.trim();
    if (!q || queryRunning) return;
    setQueryRunning(true);
    try {
      const selected = results.slice(0, 3).map((r) => r.file_path);
      const res = await fetch(`${API_BASE_URL}/chat/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: q,
          top_k: 5,
          selected_files: selected,
          mode: 'retrieval',
        }),
      });
      if (!res.ok) {
        setQueryResponse('Could not run quick query right now.');
        return;
      }
      const payload = await res.json();
      const answer = String(payload.answer || '').trim();
      setQueryResponse(answer ? answer.slice(0, 360) : 'No response returned.');
    } catch {
      setQueryResponse('Could not run quick query right now.');
    } finally {
      setQueryRunning(false);
    }
  }

  const isElectron = Boolean(window.miniMode);

  function dismiss(): void {
    if (window.miniMode?.dismiss) {
      window.miniMode.dismiss();
      return;
    }
    // In browser mode, navigate to chat instead of trying window.close()
    window.location.href = '/chat';
  }

  async function activateCurrent(): Promise<void> {
    const selected = items[activeIndex];
    if (!selected) return;
    if (selected.kind === 'file' && selected.data) {
      await openFileInMain(selected.data.file_path);
      return;
    }
    if (selected.kind === 'ask') {
      await runQuickQuery(input);
    }
  }

  return (
    <div
      className="min-h-screen w-full bg-transparent flex items-start justify-center pt-20"
      onMouseDown={(e) => {
        if (isElectron && e.currentTarget === e.target) {
          dismiss();
        }
      }}
    >
      <div
        className="w-[560px] max-w-[92vw] max-h-[420px] rounded-2xl border border-white/15 bg-slate-900/78 text-slate-100 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur-[20px]"
        style={{
          animation: 'mini-in 120ms ease-out',
          fontFamily: 'ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',
        }}
        onBlur={(e) => {
          if (isElectron && e.relatedTarget && !e.currentTarget.contains(e.relatedTarget as Node)) {
            dismiss();
          }
        }}
        tabIndex={-1}
        onKeyDown={async (e) => {
          if (e.key === 'Escape') {
            e.preventDefault();
            dismiss();
            return;
          }
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (items.length > 0) {
              setActiveIndex((i) => (i + 1) % items.length);
            }
            return;
          }
          if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (items.length > 0) {
              setActiveIndex((i) => (i - 1 + items.length) % items.length);
            }
            return;
          }
          if (e.key === 'Enter') {
            e.preventDefault();
            await activateCurrent();
          }
        }}
      >
        <div className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
          <Search className="h-4 w-4 text-slate-300" />
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setQueryResponse('');
            }}
            placeholder="Search files or ask anything..."
            className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-400 outline-none"
          />
        </div>

        <div className="px-2 py-2 space-y-1">
          {items.slice(0, 6).map((item, idx) => {
            const active = idx === activeIndex;
            if (item.kind === 'file' && item.data) {
              return (
                <button
                  key={`${item.data.file_path}-${idx}`}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => void openFileInMain(item.data!.file_path)}
                  className={`w-full rounded-lg px-3 py-2 text-left transition ${
                    active ? 'bg-cyan-400/15 ring-1 ring-cyan-300/35' : 'hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="truncate text-sm font-medium text-slate-100">{item.data.file_name}</div>
                    <div className="truncate text-[11px] text-slate-400 font-mono">{item.data.parent}</div>
                  </div>
                  {!!item.data.snippet && (
                    <div className="mt-1 truncate text-xs text-slate-300/85">{item.data.snippet}</div>
                  )}
                </button>
              );
            }
            return (
              <button
                key={`ask-${idx}`}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => void runQuickQuery(input)}
                className={`w-full rounded-lg px-3 py-2 text-left transition ${
                  active ? 'bg-violet-400/15 ring-1 ring-violet-300/35' : 'hover:bg-white/5'
                }`}
              >
                <div className="flex items-center gap-2 text-sm text-slate-100">
                  <MessageCircle className="h-4 w-4" />
                  <span className="truncate">Ask: "{input.trim()}"</span>
                </div>
              </button>
            );
          })}

          {items.length === 0 && input.trim() && (
            <div className="px-3 py-4 text-xs text-slate-400">No matching in-context files yet.</div>
          )}

          {!!queryResponse && (
            <div className="mx-1 rounded-lg border border-cyan-300/20 bg-cyan-500/5 px-3 py-2 text-xs text-slate-200">
              {queryResponse}
            </div>
          )}

          {queryRunning && (
            <div className="px-3 py-2 text-xs text-slate-400">Running quick query...</div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-white/10 px-3 py-2">
          <div className="text-[11px] text-slate-400">Esc dismisses • ↑↓ navigate • Enter selects</div>
          <button
            className="inline-flex items-center gap-2 rounded-md border border-cyan-300/35 bg-cyan-400/10 px-3 py-1.5 text-xs text-cyan-100 hover:bg-cyan-400/20"
            onClick={focusFullApp}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open Full App
          </button>
        </div>
      </div>

      <style>{`
        @keyframes mini-in {
          from { opacity: 0; transform: scale(0.96); }
          to { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}
