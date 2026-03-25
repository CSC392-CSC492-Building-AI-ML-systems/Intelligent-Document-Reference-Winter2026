import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatContext } from '@/app/contexts/ChatContext';
import { ExclusionConfigDialog } from '@/app/components/ExclusionConfigDialog';
import { Button } from '@/app/components/ui/button';
import { Input } from '@/app/components/ui/input';
import { Label } from '@/app/components/ui/label';
import { Textarea } from '@/app/components/ui/textarea';
import { Switch } from '@/app/components/ui/switch';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/app/components/ui/alert-dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/app/components/ui/tabs';
import { RadioGroup, RadioGroupItem } from '@/app/components/ui/radio-group';
import { Slider } from '@/app/components/ui/slider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/app/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/app/components/ui/select';
import { ArrowLeft, Moon, Sun, Save, X, FolderOpen, FilePlus, RefreshCw, Trash2, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

export function SettingsPage() {
  const navigate = useNavigate();
  const {
    modelProvider,
    setModelProvider,
    inferenceBackend,
    setInferenceBackend,
    embeddingBackend,
    setEmbeddingBackend,
    selectedModel,
    setSelectedModel,
    embeddingModel,
    setEmbeddingModel,
    embeddingDimension,
    setEmbeddingDimension,
    availableInferenceModels,
    availableEmbeddingModels,
    availableEmbeddingDimensions,
    localOllamaModels,
    localEndpoint,
    setLocalEndpoint,
    refreshOllamaModels,
    refreshEmbeddingDimensions,
    apiKeys,
    setApiKey,
    temperature,
    setTemperature,
    contextSize,
    setContextSize,
    topK,
    setTopK,

    systemPrompt,
    setSystemPrompt,
    darkMode,
    setDarkMode,

    indexedFiles,
    indexedDirectories,
    toggleIndexedFile,
    excludedFiles,
    excludedDirectories,
    exclusionPatterns,
    addIndexedDirectory,
    removeIndexedDirectory,
    addExcludedDirectory,
    removeExcludedDirectory,
    saveFileIndexingConfig,
    saveSettings,
    saveSetting,
    pickFolder,
    pickFiles,
    reindexRequired,
    outdatedFileCount,
    loadFiles,
    refreshPipelineStatus,
  } = useChatContext();

  const [isSaving, setIsSaving] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [isBrowsingExclusion, setIsBrowsingExclusion] = useState(false);
  const [isBrowsingFiles, setIsBrowsingFiles] = useState(false);
  const [isScanningLocalModels, setIsScanningLocalModels] = useState(false);
  const [isRefreshingEmbeddingDims, setIsRefreshingEmbeddingDims] = useState(false);
  const [isReindexing, setIsReindexing] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [isClearDialogOpen, setIsClearDialogOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');

  const currentSnapshot = useMemo(
    () =>
      createIndexingSnapshot(
        indexedFiles,
        indexedDirectories,
        excludedFiles,
        excludedDirectories,
        exclusionPatterns
      ),
    [indexedFiles, indexedDirectories, excludedFiles, excludedDirectories, exclusionPatterns]
  );

  const [savedSnapshot, setSavedSnapshot] = useState<IndexingSnapshot>(currentSnapshot);

  const hasUnsavedIndexingChanges = useMemo(
    () => !snapshotsEqual(currentSnapshot, savedSnapshot),
    [currentSnapshot, savedSnapshot]
  );

  useEffect(() => {
    if (!hasUnsavedIndexingChanges) {
      setSavedSnapshot(currentSnapshot);
    }
  }, [currentSnapshot, hasUnsavedIndexingChanges]);

  const showUnsavedIndexingWarning = useCallback(() => {
    toast.error('Unsaved file indexing changes', {
      description:
        'Save Configuration to apply your updates, or undo them before leaving this page.',
    });
  }, []);

  useEffect(() => {
    if (!hasUnsavedIndexingChanges) return;

    window.history.pushState(null, '', window.location.href);

    const handlePopState = () => {
      showUnsavedIndexingWarning();
      window.history.pushState(null, '', window.location.href);
    };

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, [hasUnsavedIndexingChanges, showUnsavedIndexingWarning]);

  useBeforeUnload(
    useCallback(
      (event) => {
        if (!hasUnsavedIndexingChanges) return;
        event.preventDefault();
        event.returnValue = '';
      },
      [hasUnsavedIndexingChanges]
    )
  );

  const guardNavigate = useCallback(
    (target: string) => {
      if (hasUnsavedIndexingChanges) {
        showUnsavedIndexingWarning();
        return;
      }
      navigate(target);
    },
    [hasUnsavedIndexingChanges, navigate, showUnsavedIndexingWarning]
  );

  const handleDarkModeChange = async (enabled: boolean) => {
    setDarkMode(enabled);
    await saveSetting('darkMode', enabled);
  };

  const handleSaveSettings = async () => {
    setIsSavingSettings(true);
    try {
      await saveSettings();
      toast.success('Settings saved successfully!');
    } catch (error) {
      toast.error(`Error saving settings: ${error}`);
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleBrowseFolder = async () => {
    setIsBrowsing(true);
    try {
      const result = await pickFolder();
      if (result?.status === 'selected' && result.path) {
        addIndexedDirectory(result.path);
      } else if (result?.status === 'error') {
        toast.error('Could not use that folder.');
      }
    } catch (err) {
      toast.error(`Browse failed: ${err instanceof Error ? err.message : err}`);
    } finally {
      setIsBrowsing(false);
    }
  };

  const handleBrowseFiles = async () => {
    setIsBrowsingFiles(true);
    try {
      const result = await pickFiles();
      if (result?.status === 'selected' && result.paths && result.paths.length > 0) {
        for (const filePath of result.paths) {
          if (!indexedFiles.includes(filePath)) {
            toggleIndexedFile(filePath);
          }
        }
      } else if (result?.status === 'error') {
        toast.error('Could not pick files.');
      }
    } catch (err) {
      toast.error(`Browse failed: ${err instanceof Error ? err.message : err}`);
    } finally {
      setIsBrowsingFiles(false);
    }
  };

  const handleBrowseExclusionFolder = async () => {
    setIsBrowsingExclusion(true);
    try {
      const result = await pickFolder();
      if (result?.status === 'selected' && result.path) {
        addExcludedDirectory(result.path);
      } else if (result?.status === 'error') {
        toast.error('Could not use that folder.');
      }
    } catch (err) {
      toast.error(`Browse failed: ${err instanceof Error ? err.message : err}`);
    } finally {
      setIsBrowsingExclusion(false);
    }
  };

  const handleSaveFileIndexing = async () => {
    setIsSaving(true);
    try {
      const inclusionFiles = indexedFiles.filter(f => !f.endsWith('/'));
      const exclusionFiles = excludedFiles.filter(f => !f.endsWith('/'));
      const directoriesToSave = [...indexedDirectories];
      const contextFiles = inclusionFiles;

      const success = await saveFileIndexingConfig({
        inclusion: {
          files: inclusionFiles,
          directories: directoriesToSave,
        },
        exclusion: {
          files: exclusionFiles,
          directories: excludedDirectories,
          patterns: exclusionPatterns,
        },
        context: {
          files: contextFiles,
        },
      });

      if (success) {
        toast.success('File indexing configuration saved successfully!');
      } else {
        toast.error('Failed to save file indexing configuration.');
      }
    } catch (error) {
      toast.error(`Error saving configuration: ${error}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleScanLocalModels = async () => {
    setIsScanningLocalModels(true);
    try {
      const models = await refreshOllamaModels(localEndpoint);
      if (models.length > 0) {
        toast.success(`Found ${models.length} local model${models.length === 1 ? '' : 's'}.`);
      } else {
        toast.info('No local models found at that Ollama endpoint.');
      }
    } catch (error) {
      toast.error(`Failed to scan local models: ${error}`);
    } finally {
      setIsScanningLocalModels(false);
    }
  };

  const handleRefreshEmbeddingDimensions = async () => {
    setIsRefreshingEmbeddingDims(true);
    try {
      const dims = await refreshEmbeddingDimensions(embeddingBackend, embeddingModel, {
        forceDefault: true,
        forceRefresh: true,
      });
      if (dims.length > 0) {
        toast.success('Embedding dimensions refreshed for selected model.');
      } else {
        toast.info('No embedding dimensions available for selected model.');
      }
    } catch (error) {
      toast.error(`Failed to refresh embedding dimensions: ${error}`);
    } finally {
      setIsRefreshingEmbeddingDims(false);
    }
  };

  const handleReindex = async () => {
    setIsReindexing(true);
    const pollId = window.setInterval(() => {
      loadFiles().catch((error) => {
        console.error('Failed to refresh file statuses during reindex:', error);
      });
    }, 1000);
    try {
      const res = await fetch('/settings/reindex', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        toast.success(data.message || 'Reindex complete!');
      } else {
        toast.error(data.detail || 'Reindex failed.');
      }
    } catch (error) {
      toast.error(`Reindex failed: ${error instanceof Error ? error.message : error}`);
    } finally {
      window.clearInterval(pollId);
      await loadFiles();
      await refreshPipelineStatus();
      setIsReindexing(false);
    }
  };

  const handleClearIndexes = async () => {
    setIsClearDialogOpen(false);
    setIsClearing(true);
    try {
      const res = await fetch('/settings/clear-indexes', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        toast.success(data.message || 'All indexes cleared.');
      } else {
        toast.error(data.detail || 'Failed to clear indexes.');
      }
    } catch (error) {
      toast.error(`Clear failed: ${error instanceof Error ? error.message : error}`);
    } finally {
      setIsClearing(false);
    }
  };

  const embeddingProviderLabel =
    embeddingBackend === 'local'
      ? 'Ollama'
      : embeddingBackend === 'gemini'
        ? 'Gemini API'
        : embeddingBackend === 'voyage'
          ? 'Voyage API'
          : 'OpenAI API';

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card">
        <div className="px-4 py-4 flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/chat')} className="cursor-pointer">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-2xl font-semibold">Settings</h1>
        </div>
      </div>

      {/* Settings Content */}
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {reindexRequired && (
          <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900">
            <p className="text-sm font-medium">Reindex required after embedding configuration change</p>
            <p className="text-xs mt-1">
              {outdatedFileCount > 0
                ? `${outdatedFileCount} file${outdatedFileCount === 1 ? '' : 's'} marked outdated. Run reindexing to rebuild vectors.`
                : 'Some vectors are outdated. Run reindexing to rebuild vectors.'}
            </p>
          </div>
        )}
        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as SettingsTab)} className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="general" className="cursor-pointer">General Settings</TabsTrigger>
            <TabsTrigger value="models" className="cursor-pointer">Model Configuration</TabsTrigger>
            <TabsTrigger value="indexing" className="cursor-pointer">File Indexing</TabsTrigger>
            <TabsTrigger value="advanced" className="cursor-pointer">Advanced Settings</TabsTrigger>
          </TabsList>

          {/* General Settings */}
          <TabsContent value="general" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Appearance</CardTitle>
                <CardDescription>Customize the look and feel of the application</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="dark-mode">Dark Mode</Label>
                    <p className="text-sm text-muted-foreground">
                      Switch between light and dark theme
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {darkMode ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
                    <Switch
                      id="dark-mode"
                      checked={darkMode}
                      onCheckedChange={handleDarkModeChange}
                      className="cursor-pointer"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>System Prompt</CardTitle>
                <CardDescription>
                  Customize the system prompt that guides the AI's behavior
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="system-prompt">System Prompt</Label>
                  <Textarea
                    id="system-prompt"
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    placeholder="You are a helpful AI assistant..."
                    className="min-h-[120px]"
                  />
                  <p className="text-sm text-muted-foreground">
                    This prompt will be used to set the AI's behavior and personality
                  </p>
                </div>
              </CardContent>
            </Card>



            <div className="flex justify-end">
              <Button onClick={handleSaveSettings} disabled={isSavingSettings} className="cursor-pointer">
                {isSavingSettings ? 'Saving...' : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Settings
                  </>
                )}
              </Button>
            </div>
          </TabsContent>

          {/* Model Configuration */}
          <TabsContent value="models" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Model Provider</CardTitle>
                <CardDescription>
                  Choose between local models or online API services
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <RadioGroup
                  value={modelProvider}
                  onValueChange={(value) => setModelProvider(value as 'local' | 'online')}
                  className="gap-4"
                >
                  <div className="flex items-center space-x-2 border border-input rounded-lg p-4 cursor-pointer hover:bg-accent">
                    <RadioGroupItem value="online" id="online" className="border-black cursor-pointer" />
                    <Label htmlFor="online" className="cursor-pointer flex-1">Online Models</Label>
                  </div>
                  <div className="flex items-center space-x-2 border border-input rounded-lg p-4 cursor-pointer hover:bg-accent">
                    <RadioGroupItem value="local" id="local" className="border-black cursor-pointer" />
                    <Label htmlFor="local" className="cursor-pointer flex-1">Local Models</Label>
                  </div>
                </RadioGroup>

                <div className="grid md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Inference Backend</Label>
                    <Select value={inferenceBackend} onValueChange={(value) => setInferenceBackend(value as 'local' | 'api' | 'gemini' | 'voyage')}>
                      <SelectTrigger className="cursor-pointer">
                        <SelectValue placeholder="Choose inference backend" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gemini" className="cursor-pointer">Google Gemini</SelectItem>
                        <SelectItem value="local" className="cursor-pointer">Local (Ollama)</SelectItem>
                        <SelectItem value="api" className="cursor-pointer">OpenAI API</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Embedding Backend</Label>
                    <Select value={embeddingBackend} onValueChange={(value) => setEmbeddingBackend(value as 'local' | 'api' | 'gemini' | 'voyage')}>
                      <SelectTrigger className="cursor-pointer">
                        <SelectValue placeholder="Choose embedding backend" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gemini" className="cursor-pointer">Google Gemini</SelectItem>
                        <SelectItem value="local" className="cursor-pointer">Local (Ollama)</SelectItem>
                        <SelectItem value="api" className="cursor-pointer">OpenAI API</SelectItem>
                        <SelectItem value="voyage" className="cursor-pointer">Voyage AI</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {(inferenceBackend === 'local' || embeddingBackend === 'local') && (
                  <div className="space-y-3 rounded-lg border border-input p-4">
                    <div className="space-y-2">
                      <Label htmlFor="endpoint">Ollama Endpoint</Label>
                      <Input
                        id="endpoint"
                        type="url"
                        placeholder="http://localhost:11434"
                        value={localEndpoint}
                        onChange={(e) => setLocalEndpoint(e.target.value)}
                      />
                      <p className="text-sm text-muted-foreground">
                        Use your local Ollama host. Then scan to list installed models.
                      </p>
                    </div>

                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm text-muted-foreground">
                        {localOllamaModels.length > 0
                          ? `${localOllamaModels.length} local model${localOllamaModels.length === 1 ? '' : 's'} detected`
                          : 'No local models detected yet'}
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={handleScanLocalModels}
                        disabled={isScanningLocalModels}
                        className="cursor-pointer"
                      >
                        <RefreshCw className={`h-4 w-4 mr-2 ${isScanningLocalModels ? 'animate-spin' : ''}`} />
                        {isScanningLocalModels ? 'Scanning...' : 'Scan Local Models'}
                      </Button>
                    </div>
                  </div>
                )}

                <div className="grid md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Inference Model</Label>
                    <Select value={selectedModel} onValueChange={setSelectedModel}>
                      <SelectTrigger className="cursor-pointer">
                        <SelectValue placeholder="Choose inference model" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableInferenceModels.map((modelName) => (
                          <SelectItem key={modelName} value={modelName} className="cursor-pointer">
                            {modelName}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Embedding Model</Label>
                    <Select value={embeddingModel} onValueChange={setEmbeddingModel}>
                      <SelectTrigger className="cursor-pointer">
                        <SelectValue placeholder="Choose embedding model" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableEmbeddingModels.map((modelName) => (
                          <SelectItem key={modelName} value={modelName} className="cursor-pointer">
                            {modelName}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-3 rounded-lg border border-input p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <Label>Embedding Dimension Configuration</Label>
                      <p className="text-sm text-muted-foreground">
                        Active provider: {embeddingProviderLabel} | Active model: {embeddingModel}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleRefreshEmbeddingDimensions}
                      disabled={isRefreshingEmbeddingDims}
                      className="cursor-pointer"
                    >
                      <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshingEmbeddingDims ? 'animate-spin' : ''}`} />
                      {isRefreshingEmbeddingDims ? 'Refreshing...' : 'Use Model Default'}
                    </Button>
                  </div>

                  <div className="space-y-2">
                    <Label>Embedding Dimension</Label>
                    <Select
                      value={String(embeddingDimension)}
                      onValueChange={(value) => setEmbeddingDimension(Number(value))}
                    >
                      <SelectTrigger className="cursor-pointer">
                        <SelectValue placeholder="Choose embedding dimension" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableEmbeddingDimensions.map((dim) => (
                          <SelectItem key={dim} value={String(dim)} className="cursor-pointer">
                            {dim}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-sm text-muted-foreground">
                      Defaults are model-aware; changing this lets you override within supported sizes.
                    </p>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="gemini-key">Google API Key</Label>
                    <Input
                      id="gemini-key"
                      type="password"
                      placeholder="AI..."
                      value={apiKeys.gemini || ''}
                      onChange={(e) => setApiKey('gemini', e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="openai-key">OpenAI API Key</Label>
                    <Input
                      id="openai-key"
                      type="password"
                      placeholder="sk-..."
                      value={apiKeys.openai || ''}
                      onChange={(e) => setApiKey('openai', e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="voyage-key">Voyage API Key</Label>
                    <Input
                      id="voyage-key"
                      type="password"
                      placeholder="pa-..."
                      value={apiKeys.voyage || ''}
                      onChange={(e) => setApiKey('voyage', e.target.value)}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="flex justify-end">
              <Button onClick={handleSaveSettings} disabled={isSavingSettings} className="cursor-pointer">
                {isSavingSettings ? 'Saving...' : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Settings
                  </>
                )}
              </Button>
            </div>
          </TabsContent>

          {/* File Indexing */}
          <TabsContent value="indexing" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Document Indexing</CardTitle>
                <CardDescription>
                  Select files and folders to include or exclude from RAG retrieval
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Inclusion List */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium">Inclusion List</h3>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleBrowseFolder}
                        disabled={isBrowsing}
                        title="Add a folder to include"
                        className="cursor-pointer"
                      >
                        <FolderOpen className="h-4 w-4 mr-1" />
                        {isBrowsing ? 'Opening...' : 'Add Folder'}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleBrowseFiles}
                        disabled={isBrowsingFiles}
                        title="Add individual files to include"
                        className="cursor-pointer"
                      >
                        <FilePlus className="h-4 w-4 mr-1" />
                        {isBrowsingFiles ? 'Opening...' : 'Add Files'}
                      </Button>
                    </div>
                  </div>

                  {/* Show included directories */}
                  {indexedDirectories.length > 0 && (
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">Included folders:</Label>
                      <div className="flex flex-wrap gap-2">
                        {indexedDirectories.map((dir) => (
                          <div
                            key={dir}
                            className="flex items-center gap-2 px-3 py-1.5 bg-primary/10 rounded-md border border-primary/20"
                          >
                            <span className="text-sm">{dir}</span>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-5 w-5 cursor-pointer"
                              onClick={() => removeIndexedDirectory(dir)}
                              title="Remove from inclusion"
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Show included individual files */}
                  {indexedFiles.length > 0 && (
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">Included files:</Label>
                      <div className="flex flex-wrap gap-2">
                        {indexedFiles.map((file) => (
                          <div
                            key={file}
                            className="flex items-center gap-2 px-3 py-1.5 bg-primary/10 rounded-md border border-primary/20"
                          >
                            <span className="text-sm">{file.split('/').pop()}</span>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-5 w-5 cursor-pointer"
                              onClick={() => toggleIndexedFile(file)}
                              title={file}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Exclusion List */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium">Exclusion List</h3>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleBrowseExclusionFolder}
                        disabled={isBrowsingExclusion}
                        title="Add a folder to exclude"
                        className="cursor-pointer"
                      >
                        <FolderOpen className="h-4 w-4 mr-1" />
                        {isBrowsingExclusion ? 'Opening...' : 'Browse'}
                      </Button>
                      <ExclusionConfigDialog />
                    </div>
                  </div>

                  {/* Show excluded directories */}
                  {excludedDirectories.length > 0 && (
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">Excluded Folders:</Label>
                      <div className="flex flex-wrap gap-2">
                        {excludedDirectories.map((dir) => (
                          <div
                            key={dir}
                            className="flex items-center gap-2 px-3 py-1.5 bg-destructive/10 rounded-md border border-destructive/20"
                          >
                            <span className="text-sm">{dir}</span>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-5 w-5 cursor-pointer"
                              onClick={() => removeExcludedDirectory(dir)}
                              title="Remove from exclusion"
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {excludedFiles.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      {excludedFiles.length} file{excludedFiles.length !== 1 ? 's' : ''} excluded
                    </p>
                  )}
                </div>

                <div className="flex items-center justify-between pt-4 border-t">
                  <p className="text-sm text-muted-foreground">
                    Included files will be used for retrieval-augmented generation, while excluded files will be ignored.
                  </p>
                  <Button
                    onClick={handleSaveFileIndexing}
                    disabled={isSaving}
                    className="ml-4 cursor-pointer"
                  >
                    {isSaving ? (
                      <>
                        <span className="animate-spin mr-2">&#8987;</span>
                        Saving...
                      </>
                    ) : (
                      <>
                        <Save className="h-4 w-4 mr-2" />
                        Save Configuration
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Index Management Card */}
            <Card>
              <CardHeader>
                <CardTitle>Index Management</CardTitle>
                <CardDescription>
                  Reindex files or clear all stored chunks and embeddings
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Reindex All Files</p>
                    <p className="text-xs text-muted-foreground">
                      Re-embed and re-store all configured files. Useful after switching embedding models.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    onClick={handleReindex}
                    disabled={isReindexing}
                    className="cursor-pointer"
                  >
                    <RotateCcw className={`h-4 w-4 mr-2 ${isReindexing ? 'animate-spin' : ''}`} />
                    {isReindexing ? 'Reindexing...' : 'Reindex'}
                  </Button>
                </div>
                <div className="flex items-center justify-between pt-3 border-t">
                  <div>
                    <p className="text-sm font-medium text-destructive">Clear All Indexes</p>
                    <p className="text-xs text-muted-foreground">
                      Remove all chunks, vectors, and file records from the database.
                    </p>
                  </div>
                  <Button
                    variant="destructive"
                    onClick={() => setIsClearDialogOpen(true)}
                    disabled={isClearing}
                    className="cursor-pointer"
                  >
                    <Trash2 className={`h-4 w-4 mr-2 ${isClearing ? 'animate-spin' : ''}`} />
                    {isClearing ? 'Clearing...' : 'Clear Indexes'}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <AlertDialog open={isClearDialogOpen} onOpenChange={setIsClearDialogOpen}>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Clear all indexes?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This removes all indexed chunks, vectors, and file records from the database.
                    Your inclusion/exclusion configuration is preserved.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel className="cursor-pointer" disabled={isClearing}>
                    Cancel
                  </AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleClearIndexes}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90 cursor-pointer"
                    disabled={isClearing}
                  >
                    {isClearing ? 'Clearing...' : 'Yes, clear indexes'}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </TabsContent>

          {/* Advanced Settings */}
          <TabsContent value="advanced" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Generation Parameters</CardTitle>
                <CardDescription>
                  Fine-tune model behavior and performance
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="temperature">Temperature</Label>
                      <span className="text-sm text-muted-foreground">{temperature}</span>
                    </div>
                    <Slider
                      id="temperature"
                      min={0}
                      max={2}
                      step={0.1}
                      value={[temperature]}
                      onValueChange={(value) => setTemperature(value[0])}
                      className="cursor-pointer"
                    />
                    <p className="text-sm text-muted-foreground">
                      Controls randomness. Lower values make output more focused and
                      deterministic.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="context">Context Size</Label>
                      <span className="text-sm text-muted-foreground">{contextSize}</span>
                    </div>
                    <Slider
                      id="context"
                      min={1024}
                      max={32768}
                      step={1024}
                      value={[contextSize]}
                      onValueChange={(value) => setContextSize(value[0])}
                      className="cursor-pointer"
                    />
                    <p className="text-sm text-muted-foreground">
                      Maximum number of tokens to use for context window.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Retrieval Settings</CardTitle>
                <CardDescription>Configure RAG retrieval behavior</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="top-k">Top-K Results</Label>
                    <span className="text-sm text-muted-foreground">{topK}</span>
                  </div>
                  <Slider
                    id="top-k"
                    min={1}
                    max={20}
                    step={1}
                    value={[topK]}
                    onValueChange={(value) => setTopK(value[0])}
                    className="cursor-pointer"
                  />
                  <p className="text-sm text-muted-foreground">
                    Number of relevant documents to retrieve per query
                  </p>
                </div>


              </CardContent>
            </Card>

            <div className="flex justify-end">
              <Button onClick={handleSaveSettings} disabled={isSavingSettings} className="cursor-pointer">
                {isSavingSettings ? 'Saving...' : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Settings
                  </>
                )}
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
