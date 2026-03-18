import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileNavigator } from '@/app/components/FileNavigator';
import { ChatMessages } from '@/app/components/ChatMessages';
import { ChatInput } from '@/app/components/ChatInput';
import { Button } from '@/app/components/ui/button';
import { Settings, PanelLeftClose, PanelLeft, Minimize2, Maximize2 } from 'lucide-react';
import { cn } from '@/app/components/ui/utils';

export function ChatPage() {
  const [showFileNav, setShowFileNav] = useState(true);
  const [composerCollapsed, setComposerCollapsed] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="flex h-screen bg-background">
      {/* File Navigator */}
      <div
        className={cn(
          'border-r bg-card transition-all duration-300',
          showFileNav ? 'w-64' : 'w-0 overflow-hidden'
        )}
      >
        {showFileNav && (
          <div className="h-full flex flex-col">
            <div className="p-4 border-b">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold">Browse Files</h2>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowFileNav(false)}
                  className="cursor-pointer"
                >
                  <PanelLeftClose className="h-4 w-4" />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Select files for conversation context
              </p>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs mt-1 cursor-pointer"
                onClick={() => navigate('/settings')}
              >
                Manage in Settings &rarr;
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <FileNavigator type="context" />
            </div>
          </div>
        )}
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="h-16 border-b flex items-center justify-between px-4 bg-card">
          <div className="flex items-center gap-2">
            {!showFileNav && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowFileNav(true)}
                className="cursor-pointer"
              >
                <PanelLeft className="h-4 w-4" />
              </Button>
            )}
            <h1 className="text-lg font-semibold">RAG Chatbot</h1>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/settings')}
            className="cursor-pointer"
          >
            <Settings className="h-4 w-4 mr-2" />
            Settings
          </Button>
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-hidden">
          <ChatMessages />
        </div>

        {/* Input Area */}
        <div
          className={cn(
            'border-t bg-card transition-all duration-200',
            composerCollapsed ? 'px-4 py-2' : 'p-4'
          )}
        >
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              {composerCollapsed ? 'Message composer is minimized' : 'Ready to ask another question'}
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="cursor-pointer"
              onClick={() => setComposerCollapsed((prev) => !prev)}
            >
              {composerCollapsed ? (
                <Maximize2 className="h-4 w-4 mr-1" />
              ) : (
                <Minimize2 className="h-4 w-4 mr-1" />
              )}
              {composerCollapsed ? 'Expand' : 'Minimize'}
            </Button>
          </div>
          {!composerCollapsed && (
            <div className="mt-3">
              <ChatInput />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
