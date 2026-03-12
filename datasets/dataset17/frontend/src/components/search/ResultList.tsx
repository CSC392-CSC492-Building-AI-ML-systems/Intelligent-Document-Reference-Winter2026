import React from 'react';
import { ResultCard } from './ResultCard';

interface Result { id: string; score: number; text: string; }
interface Props { results: Result[]; loading: boolean; }

export const ResultList: React.FC<Props> = ({ results, loading }) => {
    if (loading) return <div>Loading...</div>;
    return (
        <div className="results">
            {results.map(r => <ResultCard key={r.id} result={r} />)}
        </div>
    );
};
