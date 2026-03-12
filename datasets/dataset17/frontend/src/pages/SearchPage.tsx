import React from 'react';
import { SearchBox } from '../components/search/SearchBox';
import { ResultList } from '../components/search/ResultList';
import { useSearch } from '../hooks/useSearch';

export const SearchPage: React.FC = () => {
    const { results, loading, search } = useSearch();
    return (
        <div className="search-page">
            <h1>Document Search</h1>
            <SearchBox onSearch={search} />
            <ResultList results={results} loading={loading} />
        </div>
    );
};
