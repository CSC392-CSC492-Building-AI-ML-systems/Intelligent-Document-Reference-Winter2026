import { useState, useEffect, useCallback } from 'react';

export function useSearch() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<Error | null>(null);

    const fetchSearch = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/api/search');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            setData(await res.json());
        } catch (err) {
            setError(err as Error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchSearch(); }, []);

    return { data, loading, error, refetch: fetchSearch };
}
