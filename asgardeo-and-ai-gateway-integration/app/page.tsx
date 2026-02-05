'use client'

import { useState, useEffect } from 'react';
import ConfigurationModal, { AppConfig } from './components/ConfigurationModal';
import AgentSimulator from './components/AgentSimulator';

const defaultConfig: AppConfig = {
  orgName: '',
  clientId: '',
  targetUrl: '',
  coordinatorAgent: {
    agentId: '',
    agentSecret: ''
  },
  expertAgent: {
    agentId: '',
    agentSecret: ''
  }
};

export default function Home() {
  const [config, setConfig] = useState<AppConfig>(defaultConfig);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Ensure we're mounted before accessing localStorage
  useEffect(() => {
    setMounted(true);
  }, []);

  // Load config from session storage on mount
  useEffect(() => {
    if (!mounted) return;
    
    const savedConfig = sessionStorage.getItem('app-config');
    if (savedConfig) {
      try {
        const parsed = JSON.parse(savedConfig);
        setConfig(parsed);
      } catch (e) {
        console.error('Failed to parse saved config:', e);
      }
    } else {
      // If no config, show the configuration modal
      setIsConfigModalOpen(true);
    }
  }, [mounted]);

  const handleSaveConfig = (newConfig: AppConfig) => {
    setConfig(newConfig);
    sessionStorage.setItem('app-config', JSON.stringify(newConfig));
  };

  if (!mounted) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-orange-500"></div>
      </div>
    );
  }

  return (
    <>
      <AgentSimulator 
        config={config} 
        onOpenConfig={() => setIsConfigModalOpen(true)} 
      />
      <ConfigurationModal
        isOpen={isConfigModalOpen}
        onClose={() => setIsConfigModalOpen(false)}
        config={config}
        onSave={handleSaveConfig}
      />
    </>
  );
}
