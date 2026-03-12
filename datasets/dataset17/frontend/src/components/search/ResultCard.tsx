import React from 'react';
interface Props { result: { id: string; score: number; text: string } }
export const ResultCard: React.FC<Props> = ({ result }) => (
    <div className="result-card">
        <span className="score">{result.score.toFixed(3)}</span>
        <p>{result.text}</p>
    </div>
);
