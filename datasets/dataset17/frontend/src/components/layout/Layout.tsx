import React, { PropsWithChildren } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Footer } from './Footer';

export const Layout: React.FC<PropsWithChildren> = ({ children }) => (
    <div className="app-layout">
        <Header />
        <div className="content-area">
            <Sidebar />
            <main>{children}</main>
        </div>
        <Footer />
    </div>
);
