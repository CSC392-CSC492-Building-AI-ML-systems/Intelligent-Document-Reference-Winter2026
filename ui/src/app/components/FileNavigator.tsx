import { useState, useEffect } from 'react';
import { useChatContext, FileNode } from '@/app/contexts/ChatContext';
import { Checkbox } from '@/app/components/ui/checkbox';
import { ChevronLeft, ChevronRight, File, Folder } from 'lucide-react';
import { cn } from '@/app/components/ui/utils';

interface FileNavigatorProps {
  type: 'context' | 'indexing' | 'exclusion';
}

function getAllLeafFiles(node: FileNode): string[] {
  if (node.type === 'file') return [node.path];
  if (!node.children) return [];
  return node.children.flatMap(getAllLeafFiles);
}

function getAllPaths(node: FileNode): string[] {
  const paths = [node.path];
  if (node.children) {
    for (const child of node.children) {
      paths.push(...getAllPaths(child));
    }
  }
  return paths;
}

interface StackEntry {
  name: string;
  items: FileNode[];
}

export function FileNavigator({ type }: FileNavigatorProps) {
  const {
    fileTree,
    selectedFiles,
    toggleFileSelection,
    indexedFiles,
    toggleIndexedFile,
    excludedFiles,
    toggleExcludedFile,
  } = useChatContext();

  const [stack, setStack] = useState<StackEntry[]>([{ name: 'Files', items: fileTree }]);
  const [animKey, setAnimKey] = useState(0);
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');

  useEffect(() => {
    setStack([{ name: 'Files', items: fileTree }]);
  }, [fileTree]);

  const current = stack[stack.length - 1];

  const enterFolder = (node: FileNode) => {
    setDirection('forward');
    setAnimKey((k) => k + 1);
    setStack((prev) => [...prev, { name: node.name, items: node.children ?? [] }]);
  };

  const goBack = () => {
    setDirection('back');
    setAnimKey((k) => k + 1);
    setStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev));
  };

  const isChecked = (path: string): boolean => {
    if (type === 'context') return selectedFiles.includes(path);
    if (type === 'exclusion') return excludedFiles.includes(path);
    return indexedFiles.includes(path);
  };

  const handleToggle = (path: string) => {
    if (type === 'context') toggleFileSelection(path);
    else if (type === 'exclusion') toggleExcludedFile(path);
    else toggleIndexedFile(path);
  };

  const getFolderCheckState = (node: FileNode): boolean | 'indeterminate' => {
    if (type === 'context') {
      const leaves = getAllLeafFiles(node);
      if (leaves.length === 0) return false;
      const checkedCount = leaves.filter((p) => isChecked(p)).length;
      if (checkedCount === 0) return false;
      if (checkedCount === leaves.length) return true;
      return 'indeterminate';
    } else {
      const allPaths = getAllPaths(node);
      const childPaths = allPaths.slice(1);
      if (childPaths.length === 0) return isChecked(node.path);
      const selfChecked = isChecked(node.path);
      const checkedCount = childPaths.filter((p) => isChecked(p)).length;
      if (selfChecked && checkedCount === childPaths.length) return true;
      if (!selfChecked && checkedCount === 0) return false;
      return 'indeterminate';
    }
  };

  const handleFolderCheckboxChange = (node: FileNode, checked: boolean | 'indeterminate') => {
    const targetChecked = checked === true;
    if (type === 'context') {
      const leaves = getAllLeafFiles(node);
      for (const path of leaves) {
        if (targetChecked !== isChecked(path)) handleToggle(path);
      }
    } else {
      const allPaths = getAllPaths(node);
      for (const path of allPaths) {
        if (targetChecked !== isChecked(path)) handleToggle(path);
      }
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Back navigation header */}
      {stack.length > 1 && (
        <div className="flex items-center gap-2 px-3 py-2 border-b bg-card sticky top-0 z-10 shrink-0">
          <button
            onClick={goBack}
            className="p-1 rounded hover:bg-accent cursor-pointer"
            title="Go back"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm font-medium truncate">{current.name}</span>
        </div>
      )}

      {/* Animated content panel */}
      <div className="flex-1 overflow-hidden relative">
        <div
          key={animKey}
          className="h-full overflow-y-auto p-2"
          style={{
            animation: `${direction === 'forward' ? 'slide-in-from-right' : 'slide-in-from-left'} 0.2s ease-out`,
          }}
        >
          {current.items.length === 0 ? (
            <p className="text-xs text-muted-foreground px-2 py-4 text-center">Empty folder</p>
          ) : (
            current.items.map((node) =>
              node.type === 'folder' ? (
                <div
                  key={node.id}
                  className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-accent group"
                >
                  <Checkbox
                    id={node.id}
                    checked={getFolderCheckState(node)}
                    onCheckedChange={(checked) => handleFolderCheckboxChange(node, checked)}
                    className="h-4 w-4 cursor-pointer shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  />
                  <button
                    className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer text-left"
                    onClick={() => enterFolder(node)}
                  >
                    <Folder className="h-4 w-4 text-blue-500 shrink-0" />
                    <span className="text-sm truncate">{node.name}</span>
                  </button>
                  <button
                    onClick={() => enterFolder(node)}
                    className="p-0.5 rounded hover:bg-accent-foreground/10 cursor-pointer shrink-0"
                    title={`Open ${node.name}`}
                  >
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </button>
                </div>
              ) : (
                <div
                  key={node.id}
                  className={cn(
                    'flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-accent cursor-pointer'
                  )}
                  onClick={() => handleToggle(node.path)}
                >
                  <Checkbox
                    id={node.id}
                    checked={isChecked(node.path)}
                    onCheckedChange={() => handleToggle(node.path)}
                    className="h-4 w-4 cursor-pointer shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  />
                  <File className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-sm truncate">{node.name}</span>
                </div>
              )
            )
          )}
        </div>
      </div>
    </div>
  );
}
