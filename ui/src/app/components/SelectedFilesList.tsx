import { useChatContext } from '@/app/contexts/ChatContext';
import { File, X } from 'lucide-react';
import { Button } from '@/app/components/ui/button';
import { cn } from '@/app/components/ui/utils';

export function SelectedFilesList() {
  const { selectedFiles } = useChatContext();

  // Filter out directories - only show files (leaf nodes)
  const fileOnlyList = selectedFiles.filter(path => {
    // Directories typically end with '/' or don't have a file extension
    // For now, we'll check if it's in the fileTree as a file type
    // But simpler: if it doesn't end with '/', treat as file
    return !path.endsWith('/');
  });

  if (fileOnlyList.length === 0) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground space-y-2">
        <p>No files selected for context</p>
        <p className="text-xs">Select files in Settings → File Indexing to include them in your conversations</p>
      </div>
    );
  }

  return (
    <div className="p-2 space-y-1">
      {fileOnlyList.map((path) => {
        const fileName = path.split('/').pop() || path;
        return (
          <div
            key={path}
            className={cn(
              'flex items-center gap-2 py-2 px-3 rounded-md hover:bg-accent group',
              'border border-border'
            )}
          >
            <File className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <span className="text-sm flex-1 truncate" title={path}>
              {fileName}
            </span>
          </div>
        );
      })}
    </div>
  );
}

