import { useState } from 'react';
import { useChatContext } from '@/app/contexts/ChatContext';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/app/components/ui/dialog';
import { Button } from '@/app/components/ui/button';
import { Input } from '@/app/components/ui/input';
import { Label } from '@/app/components/ui/label';
import { Settings, X, Plus } from 'lucide-react';
import { Badge } from '@/app/components/ui/badge';

export function ExclusionConfigDialog() {
  const { exclusionPatterns, addExclusionPattern, removeExclusionPattern } = useChatContext();
  const [newPattern, setNewPattern] = useState('');
  const [open, setOpen] = useState(false);

  const handleAddPattern = () => {
    if (newPattern.trim()) {
      addExclusionPattern(newPattern.trim());
      setNewPattern('');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAddPattern();
    }
  };

  const commonPatterns = [
    '.env',
    '.env.local',
    'node_modules/',
    '.git/',
    '*.log',
    '.DS_Store',
    'package-lock.json',
    'yarn.lock',
  ];

  const addCommonPattern = (pattern: string) => {
    if (!exclusionPatterns.includes(pattern)) {
      addExclusionPattern(pattern);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2 border-black">
          <Settings className="h-4 w-4" />
          Exclusion Config
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>Exclusion Configuration</DialogTitle>
          <DialogDescription>
            Configure file patterns, extensions, and specific files to exclude from indexing.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Add Pattern Input */}
          <div className="space-y-2">
            <Label htmlFor="pattern">Add Exclusion Pattern</Label>
            <div className="flex gap-2">
              <Input
                id="pattern"
                placeholder="e.g., .env, *.log, node_modules/"
                value={newPattern}
                onChange={(e) => setNewPattern(e.target.value)}
                onKeyPress={handleKeyPress}
                className="border-black"
              />
              <Button onClick={handleAddPattern} size="icon" className="shrink-0">
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Supports wildcards (*) and directory patterns (/)
            </p>
          </div>

          {/* Common Patterns */}
          <div className="space-y-2">
            <Label>Quick Add (Common Patterns)</Label>
            <div className="flex flex-wrap gap-2">
              {commonPatterns.map((pattern) => (
                <Badge
                  key={pattern}
                  variant={exclusionPatterns.includes(pattern) ? "default" : "outline"}
                  className="cursor-pointer hover:bg-accent"
                  onClick={() => addCommonPattern(pattern)}
                >
                  {pattern}
                </Badge>
              ))}
            </div>
          </div>

          {/* Current Patterns */}
          <div className="space-y-2">
            <Label>Active Exclusion Patterns ({exclusionPatterns.length})</Label>
            <div className="border border-black rounded-lg p-3 max-h-[200px] overflow-y-auto">
              {exclusionPatterns.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No exclusion patterns added yet
                </p>
              ) : (
                <div className="space-y-1.5">
                  {exclusionPatterns.map((pattern, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between gap-2 p-2 rounded bg-accent/50 hover:bg-accent"
                    >
                      <span className="text-sm font-mono">{pattern}</span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={() => removeExclusionPattern(pattern)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
