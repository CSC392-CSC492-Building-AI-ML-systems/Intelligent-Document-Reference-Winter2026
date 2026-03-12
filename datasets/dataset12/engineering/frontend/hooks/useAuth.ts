import { useState, useEffect, useCallback } from 'react';

export function useAuth() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<Error | null>(null);

    const fetchAuth = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/api/auth');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            setData(await res.json());
        } catch (err) {
            setError(err as Error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchAuth(); }, []);

    return { data, loading, error, refetch: fetchAuth };
}
