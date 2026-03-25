import { useState } from 'react';
import { useChatContext, InferenceMode, ModelType } from '@/app/contexts/ChatContext';
import { Button } from '@/app/components/ui/button';
import { Textarea } from '@/app/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/app/components/ui/select';
import { Send, Search, MessageCircleQuestion, Microscope, Sparkles } from 'lucide-react';

const modeIcons = {
  retrieval: Search,
  'q&a': MessageCircleQuestion,
  'deep-research': Microscope,
};

const modeLabels = {
  retrieval: 'Retrieval',
  'q&a': 'Q&A',
  'deep-research': 'Deep Research',
};

const modelLabels = {
  'gpt-4': 'GPT-4',
  'gemini-2.5': 'Gemini 2.5',
  'claude-3': 'Claude 3',
  'llama-3': 'Llama 3',
};

export function ChatInput() {
  const { inferenceMode, setInferenceMode, selectedModel, setSelectedModel, sendMessage, indexedFiles, indexedDirectories, pipelineReady, indexedChunkCount } =
    useChatContext();
  const [input, setInput] = useState('');

  // Allow chatting if either the YAML config lists files/dirs OR the backend has indexed chunks
  const canChat = indexedFiles.length > 0 || indexedDirectories.length > 0 || (pipelineReady && indexedChunkCount > 0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) {
      const message = input.trim();
      setInput('');
      await sendMessage(message);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!canChat) {
    return (
      <div className="space-y-3">
        <div className="relative">
          <Textarea
            disabled
            placeholder={pipelineReady ? "No documents indexed yet. Upload files in Settings → File Indexing." : "Connecting to backend..."}
            className="min-h-[120px] resize-none pr-4 pb-16 opacity-50 cursor-not-allowed"
          />
          <div className="absolute bottom-2 left-2 right-2 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">
              {pipelineReady
                ? "Index some documents first via Settings → File Indexing"
                : "Waiting for backend to start..."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="relative">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message here..."
          className="min-h-[120px] resize-none pr-4 pb-16"
        />
        
        <div className="absolute bottom-2 left-2 right-2 flex items-center gap-2">
          <Select value={inferenceMode} onValueChange={(value) => setInferenceMode(value as InferenceMode)}>
            <SelectTrigger className="w-[160px] h-9 border-black cursor-pointer">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(modeIcons) as InferenceMode[]).map((mode) => {
                const Icon = modeIcons[mode];
                return (
                  <SelectItem key={mode} value={mode} className="cursor-pointer">
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4" />
                      <span>{modeLabels[mode]}</span>
                    </div>
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>

          <Select value={selectedModel} onValueChange={(value) => setSelectedModel(value as ModelType)}>
            <SelectTrigger className="w-[160px] h-9 border-black cursor-pointer">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(modelLabels) as ModelType[]).map((model) => (
                <SelectItem key={model} value={model} className="cursor-pointer">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4" />
                    <span>{modelLabels[model]}</span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex-1" />

          <Button type="submit" size="sm" disabled={!input.trim()} className="cursor-pointer">
            <Send className="h-4 w-4 mr-2" />
            Send
          </Button>
        </div>
      </div>

      <div className="text-xs text-muted-foreground">
        Press <kbd className="px-1.5 py-0.5 bg-muted rounded border">Enter</kbd> to send,{' '}
        <kbd className="px-1.5 py-0.5 bg-muted rounded border">Shift</kbd> +{' '}
        <kbd className="px-1.5 py-0.5 bg-muted rounded border">Enter</kbd> for new line
      </div>
    </form>
  );
}