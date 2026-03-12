import { useState, useCallback } from 'react';

interface Result { id: string; score: number; text: string; }

export function useSearch() {
    const [results, setResults] = useState<Result[]>([]);
    const [loading, setLoading] = useState(false);

    const search = useCallback(async (query: string) => {
        setLoading(true);
        try {
            const res = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, top_k: 10 }),
            });
            const data = await res.json();
            setResults(data.results);
        } finally {
            setLoading(false);
        }
    }, []);

    return { results, loading, search };
}
