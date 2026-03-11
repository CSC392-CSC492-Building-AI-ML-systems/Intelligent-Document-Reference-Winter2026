import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatContext } from '@/app/contexts/ChatContext';
import { ExclusionConfigDialog } from '@/app/components/ExclusionConfigDialog';
import { Button } from '@/app/components/ui/button';
import { Input } from '@/app/components/ui/input';
import { Label } from '@/app/components/ui/label';
import { Textarea } from '@/app/components/ui/textarea';
import { Switch } from '@/app/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/app/components/ui/tabs';
import { RadioGroup, RadioGroupItem } from '@/app/components/ui/radio-group';
import { Slider } from '@/app/components/ui/slider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/app/components/ui/card';
import { ArrowLeft, Moon, Sun, Save, X, FolderOpen, FilePlus } from 'lucide-react';
import { toast } from 'sonner';

export function SettingsPage() {
  const navigate = useNavigate();
  const {
    modelProvider,
    setModelProvider,
    localEndpoint,
    setLocalEndpoint,
    apiKeys,
    setApiKey,
    temperature,
    setTemperature,
    contextSize,
    setContextSize,
    systemPrompt,
    setSystemPrompt,
    darkMode,
    setDarkMode,
    userInfo,
    setUserInfo,
    syncWatcherPaths,
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
  } = useChatContext();

  const [isSaving, setIsSaving] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [isBrowsingExclusion, setIsBrowsingExclusion] = useState(false);
  const [isBrowsingFiles, setIsBrowsingFiles] = useState(false);

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
        try {
          await syncWatcherPaths(directoriesToSave);
        } catch (err) {
          console.warn('Watcher sync failed:', err);
          toast.warning(`Configuration saved. Watcher sync failed: ${err instanceof Error ? err.message : err}`);
        }
      }

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
        <Tabs defaultValue="general" className="w-full">
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

            <Card>
              <CardHeader>
                <CardTitle>User Information</CardTitle>
                <CardDescription>
                  Provide context about yourself to personalize responses
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="user-info">User Information</Label>
                  <Textarea
                    id="user-info"
                    value={userInfo}
                    onChange={(e) => setUserInfo(e.target.value)}
                    placeholder="Enter information about yourself, your role, preferences, etc."
                    className="min-h-[100px]"
                  />
                  <p className="text-sm text-muted-foreground">
                    This information will help the AI provide more personalized responses
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

                {modelProvider === 'local' ? (
                  <div className="space-y-2">
                    <Label htmlFor="endpoint">Local Inference Endpoint</Label>
                    <Input
                      id="endpoint"
                      type="url"
                      placeholder="http://localhost:8000"
                      value={localEndpoint}
                      onChange={(e) => setLocalEndpoint(e.target.value)}
                    />
                    <p className="text-sm text-muted-foreground">
                      Enter the URL of your local inference server (e.g., Ollama, LM Studio)
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="gpt4-key">OpenAI API Key (GPT-4)</Label>
                      <Input
                        id="gpt4-key"
                        type="password"
                        placeholder="sk-..."
                        value={apiKeys['gpt-4'] || ''}
                        onChange={(e) => setApiKey('gpt-4', e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="gemini-key">Google API Key (Gemini 2.5)</Label>
                      <Input
                        id="gemini-key"
                        type="password"
                        placeholder="AI..."
                        value={apiKeys['gemini-2.5'] || ''}
                        onChange={(e) => setApiKey('gemini-2.5', e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="claude-key">Anthropic API Key (Claude 3)</Label>
                      <Input
                        id="claude-key"
                        type="password"
                        placeholder="sk-ant-..."
                        value={apiKeys['claude-3'] || ''}
                        onChange={(e) => setApiKey('claude-3', e.target.value)}
                      />
                    </div>
                  </div>
                )}
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
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="top-k">Top-K Results</Label>
                  <Input id="top-k" type="number" defaultValue="5" min="1" max="20" />
                  <p className="text-sm text-muted-foreground">
                    Number of relevant documents to retrieve
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="chunk-size">Chunk Size</Label>
                  <Input id="chunk-size" type="number" defaultValue="512" min="128" max="2048" />
                  <p className="text-sm text-muted-foreground">
                    Size of text chunks for document processing
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
