import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from 'next-themes';
import { ChatProvider, useChatContext } from '@/app/contexts/ChatContext';
import { ChatPage } from '@/app/pages/ChatPage';
import { SettingsPage } from '@/app/pages/SettingsPage';
import { MiniModePage } from '@/app/pages/MiniModePage';
import { Toaster } from '@/app/components/ui/sonner';
import { useEffect } from 'react';

function DarkModeHandler() {
  const { darkMode } = useChatContext();

  useEffect(() => {
    const root = document.documentElement;
    if (darkMode) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [darkMode]);

  return null;
}

function AppContent() {
  const { darkMode } = useChatContext();

  return (
    <>
      <DarkModeHandler />
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/mini" element={<MiniModePage />} />
      </Routes>
      <Toaster theme={darkMode ? 'dark' : 'light'} position="top-right" richColors />
    </>
  );
}

export default function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="light">
      <Router>
        <ChatProvider>
          <AppContent />
        </ChatProvider>
      </Router>
    </ThemeProvider>
  );
}
