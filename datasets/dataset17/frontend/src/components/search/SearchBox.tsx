import React, { useState } from 'react';

interface Props { onSearch: (query: string) => void; }

export const SearchBox: React.FC<Props> = ({ onSearch }) => {
    const [query, setQuery] = useState('');
    return (
        <form onSubmit={e => { e.preventDefault(); onSearch(query); }}>
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search..." />
            <button type="submit">Search</button>
        </form>
    );
};
