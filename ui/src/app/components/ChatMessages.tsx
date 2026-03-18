import { useEffect, useRef, useState, useCallback } from 'react';
import { useChatContext, Citation } from '@/app/contexts/ChatContext';
import { Avatar, AvatarFallback } from '@/app/components/ui/avatar';
import { User, Bot, FileText, ArrowDown } from 'lucide-react';
import { cn } from '@/app/components/ui/utils';
import { format } from 'date-fns';
import { Button } from '@/app/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/app/components/ui/tooltip';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';

function confidenceMeta(score: number): { label: string; note: string; className: string } {
  if (score >= 0.85) {
    return {
      label: 'Very high',
      note: 'Strong evidence overlap with your query.',
      className: 'text-emerald-700 dark:text-emerald-400',
    };
  }
  if (score >= 0.65) {
    return {
      label: 'High',
      note: 'Good support from retrieved context.',
      className: 'text-green-700 dark:text-green-400',
    };
  }
  if (score >= 0.40) {
    return {
      label: 'Medium',
      note: 'Partially relevant evidence.',
      className: 'text-amber-700 dark:text-amber-400',
    };
  }
  return {
    label: 'Low',
    note: 'Weak match; treat as low-confidence context.',
    className: 'text-rose-700 dark:text-rose-400',
  };
}

export function ChatMessages() {
  const { messages, isLoading } = useChatContext();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showScrollButton, setShowScrollButton] = useState(false);
  // Capture whether user was near bottom BEFORE the next render so the
  // post-render useEffect can scroll correctly even after scrollHeight grows.
  const wasAtBottomRef = useRef(true);

  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  // Auto-scroll after render if user was near bottom before the update
  useEffect(() => {
    if (wasAtBottomRef.current) {
      scrollToBottom();
    }
  }, [messages, isLoading, scrollToBottom]);

  const handleScroll = useCallback(() => {
    const near = isNearBottom();
    wasAtBottomRef.current = near;
    setShowScrollButton(!near);
  }, [isNearBottom]);

  const renderMarkdown = (content: string) => (
    <div className="markdown-canvas text-sm">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeSanitize]}
        components={{
          a: ({ ...props }) => (
            <a {...props} target="_blank" rel="noreferrer" />
          ),
          ul: ({ ...props }) => <ul className="list-disc" {...props} />,
          ol: ({ ...props }) => <ol className="list-decimal" {...props} />,
          li: ({ ...props }) => <li {...props} />,
          sup: ({ ...props }) => <sup className="align-super text-[0.75em]" {...props} />,
          sub: ({ ...props }) => <sub className="align-sub text-[0.75em]" {...props} />,
          code: ({ className, children, ...props }) => {
            const raw = String(children || '');
            const isBlock = (className || '').startsWith('language-') || raw.includes('\n');
            if (isBlock) {
              return (
                <code className={className} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className={cn('inline-code', className)} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );

  if (messages.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-4 max-w-md px-4">
          <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto">
            <Bot className="h-8 w-8 text-primary" />
          </div>
          <div>
            <h2 className="text-xl font-semibold mb-2">Start a Conversation</h2>
            <p className="text-muted-foreground">
              Ask me anything! Select files from the left sidebar to include them in your
              conversation context.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto overflow-x-hidden"
      >
        <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                'flex gap-4',
                message.role === 'user' ? 'justify-end' : 'justify-start'
              )}
            >
              {message.role === 'assistant' && (
                <Avatar className="h-8 w-8 mt-1">
                  <AvatarFallback className="bg-primary text-primary-foreground">
                    <Bot className="h-4 w-4" />
                  </AvatarFallback>
                </Avatar>
              )}

              <div
                className={cn(
                  'flex-1 min-w-0 space-y-2 max-w-[80%]',
                  message.role === 'user' && 'flex flex-col items-end'
                )}
              >
                <div
                  className={cn(
                    'rounded-xl px-4 py-3',
                    message.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'assistant-canvas bg-card border border-border/80 shadow-sm'
                  )}
                >
                  {message.role === 'assistant' ? (
                    renderMarkdown(message.content)
                  ) : (
                    <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
                  )}
                </div>

                {/* Citations */}
                {message.role === 'assistant' && message.citations && message.citations.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground">Sources:</p>
                    {message.citations.map((citation: Citation, idx: number) => (
                      <div
                        key={idx}
                        className="flex items-start gap-2 text-xs bg-background rounded-md p-2 border"
                      >
                        <FileText className="h-3.5 w-3.5 mt-0.5 text-blue-500 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium truncate">{citation.file_name}</span>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span
                                  className={cn(
                                    'whitespace-nowrap cursor-help',
                                    confidenceMeta(citation.relevance_score).className
                                  )}
                                >
                                  {Math.round(citation.relevance_score * 100)}% match
                                </span>
                              </TooltipTrigger>
                              <TooltipContent side="top" className="max-w-56">
                                <p className="font-medium">{confidenceMeta(citation.relevance_score).label} confidence</p>
                                <p className="mt-1">{confidenceMeta(citation.relevance_score).note}</p>
                              </TooltipContent>
                            </Tooltip>
                          </div>
                          <p className="text-muted-foreground mt-1 line-clamp-2">
                            {citation.snippet}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex items-center text-xs text-muted-foreground px-2">
                  <span>{format(message.timestamp, 'HH:mm')}</span>
                  {message.role === 'assistant' && message.processingTimeMs !== undefined && (
                    <span className="ml-2">({message.processingTimeMs}ms)</span>
                  )}
                </div>
              </div>

              {message.role === 'user' && (
                <Avatar className="h-8 w-8 mt-1">
                  <AvatarFallback className="bg-secondary">
                    <User className="h-4 w-4" />
                  </AvatarFallback>
                </Avatar>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="flex gap-4 justify-start">
              <Avatar className="h-8 w-8 mt-1">
                <AvatarFallback className="bg-primary text-primary-foreground">
                  <Bot className="h-4 w-4" />
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 space-y-2 max-w-[80%]">
                <div className="rounded-lg px-4 py-3 bg-muted">
                  <p className="text-sm text-muted-foreground">Thinking...</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Scroll to bottom button */}
      {showScrollButton && (
        <Button
          size="icon"
          variant="secondary"
          className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full shadow-lg cursor-pointer z-10"
          onClick={scrollToBottom}
        >
          <ArrowDown className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
