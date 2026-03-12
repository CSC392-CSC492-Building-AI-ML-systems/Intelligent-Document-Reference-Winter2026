import React from 'react';
import { SearchPage } from './pages/SearchPage';
import { Layout } from './components/layout/Layout';

export const App: React.FC = () => (
    <Layout>
        <SearchPage />
    </Layout>
);
