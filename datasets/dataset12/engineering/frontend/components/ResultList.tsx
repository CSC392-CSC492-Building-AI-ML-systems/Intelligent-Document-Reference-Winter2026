import React, { useState, useCallback } from 'react';

interface ResultListProps {
    className?: string;
    onAction?: (data: unknown) => void;
}

export const ResultList: React.FC<ResultListProps> = ({ className, onAction }) => {
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<unknown>(null);

    const handleAction = useCallback(async () => {
        setLoading(true);
        try {
            const response = await fetch('/api/resultlist');
            const result = await response.json();
            setData(result);
            onAction?.(result);
        } finally {
            setLoading(false);
        }
    }, [onAction]);

    return (
        <div className={className}>
            <h2>ResultList</h2>
            {loading ? <p>Loading...</p> : <pre>{JSON.stringify(data, null, 2)}</pre>}
            <button onClick={handleAction}>Refresh</button>
        </div>
    );
};
