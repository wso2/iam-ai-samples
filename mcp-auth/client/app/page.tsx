/**
 * Copyright (c) 2025, WSO2 LLC. (https://www.wso2.com).
 *
 * WSO2 LLC. licenses this file to you under the Apache License,
 * Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

// app/page.tsx - WSO2 MCP AI Agent Interface
'use client';

import { useState, useRef, useEffect } from 'react';
import { ThemeToggle } from './components/theme-toggle';
import { WSO2ProductLogo } from './components/wso2-logo';
import { WSO2Footer } from './components/wso2-footer';
import SettingsModal, {
  type MCPServerConfig,
  type AIProviderConfig,
} from './components/settings-modal';

// Types
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: Array<{
    name: string;
    input: any;
    result?: any;
  }>;
}

interface MCPTool {
  name: string;
  description: string;
  inputSchema: any;
}

interface MCPSession {
  sessionId: string;
  status: 'connecting' | 'connected' | 'error' | 'disconnected';
  serverName: string;
  mcpUrl: string;
  tools: MCPTool[];
  error?: string;
}

export default function MCPAgent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  
  // MCP Sessions
  const [mcpSessions, setMcpSessions] = useState<MCPSession[]>([]);
  
  // AI Configuration
  const [aiConfig, setAiConfig] = useState<AIProviderConfig>({
    provider: 'openai',
    apiKey: '',
    modelName: 'gpt-4o-mini',
  });
  
  // MCP Servers Configuration
  const [mcpServers, setMcpServers] = useState<MCPServerConfig[]>([]);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load configurations from localStorage
  useEffect(() => {
    const savedAIConfig = localStorage.getItem('mcp-agent-ai-config');
    if (savedAIConfig) {
      try {
        setAiConfig(JSON.parse(savedAIConfig));
      } catch (e) {
        console.error('Error loading AI config:', e);
      }
    }

    const savedServers = localStorage.getItem('mcp-agent-mcp-servers');
    if (savedServers) {
      try {
        const servers: MCPServerConfig[] = JSON.parse(savedServers);
        setMcpServers(servers);
        
        // Auto-connect to enabled servers
        servers.filter(s => s.enabled).forEach(server => {
          connectToMCP(server);
        });
      } catch (e) {
        console.error('Error loading MCP servers:', e);
      }
    }
  }, []);

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  };

  // Connect to MCP server
  const connectToMCP = async (server: MCPServerConfig) => {
    const newSessionId = `session-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    
    // Add session as connecting
    const newSession: MCPSession = {
      sessionId: newSessionId,
      status: 'connecting',
      serverName: server.name,
      mcpUrl: server.url,
      tools: [],
    };
    
    setMcpSessions(prev => [...prev, newSession]);

    try {
      // Initialize MCP session - NO session ID on first request
      const initResponse = await fetch('/api/mcp', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'x-mcp-url': server.url,
          // Don't send session ID for initialize - server creates it
          ...(server.token && { 'x-mcp-token': server.token }),
        },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'initialize',
          params: {
            protocolVersion: '2024-11-05',
            capabilities: {
              sampling: {},
              tools: {},
            },
            clientInfo: {
              name: 'mcp-agent',
              version: '1.0.0',
            },
          },
        }),
      });

      if (!initResponse.ok) {
        throw new Error(`HTTP error! status: ${initResponse.status}`);
      }

      const initResult = await initResponse.json();
      console.log('MCP Initialize result:', initResult);

      // Get session ID from response header
      const serverSessionId = initResponse.headers.get('x-session-id');
      const actualSessionId = serverSessionId || newSessionId;
      
      console.log('Client session ID:', newSessionId);
      console.log('Server session ID:', serverSessionId);
      console.log('Using session ID:', actualSessionId);

      // Update session with actual session ID
      setMcpSessions(prev =>
        prev.map(s =>
          s.sessionId === newSessionId
            ? { ...s, sessionId: actualSessionId }
            : s
        )
      );

      // Send notifications/initialized to complete the handshake
      console.log('📤 Sending notifications/initialized...');
      const initializedResponse = await fetch('/api/mcp', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-mcp-url': server.url,
          'x-session-id': actualSessionId,
          ...(server.token && { 'x-mcp-token': server.token }),
        },
        body: JSON.stringify({
          jsonrpc: '2.0',
          method: 'notifications/initialized',
        }),
      });

      if (!initializedResponse.ok) {
        console.warn('Failed to send notifications/initialized:', initializedResponse.status);
      } else {
        console.log('✅ Initialization handshake complete');
      }

      // Get available tools
      console.log('🔧 Requesting tools list...');
      console.log('   Session ID:', actualSessionId);
      
      // MCP protocol requires params field even if empty
      let toolsRequestBody = {
        jsonrpc: '2.0',
        id: 2,
        method: 'tools/list',
        params: {},
      };
      
      const toolsResponse = await fetch('/api/mcp', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'x-mcp-url': server.url,
          'x-session-id': actualSessionId,
          ...(server.token && { 'x-mcp-token': server.token }),
        },
        body: JSON.stringify(toolsRequestBody),
      });

      if (!toolsResponse.ok) {
        const errorText = await toolsResponse.text();
        console.error('❌ Tools list HTTP error:', toolsResponse.status, errorText);
        throw new Error(`HTTP error! status: ${toolsResponse.status}`);
      }

      const toolsResult = await toolsResponse.json();
      console.log('🔧 Tools list response:', toolsResult);
      
      if (toolsResult.error) {
        console.error('❌ Tools list error:', toolsResult.error);
        throw new Error(`MCP error: ${toolsResult.error.message}`);
      }

      const toolsList = toolsResult.result?.tools || [];

      // Update session with tools using actual session ID
      setMcpSessions(prev =>
        prev.map(s =>
          s.sessionId === actualSessionId
            ? { ...s, status: 'connected', tools: toolsList }
            : s
        )
      );
    } catch (error) {
      console.error('Error connecting to MCP:', error);
      setMcpSessions(prev =>
        prev.map(s =>
          s.sessionId === newSessionId || s.serverName === server.name
            ? { ...s, status: 'error', error: error instanceof Error ? error.message : 'Unknown error' }
            : s
        )
      );
    }
  };

  // Call MCP tool
  const callMCPTool = async (
    toolName: string,
    toolInput: any,
    session: MCPSession
  ): Promise<any> => {
    try {
      const server = mcpServers.find(s => s.url === session.mcpUrl);

      const response = await fetch('/api/mcp', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'x-mcp-url': session.mcpUrl,
          'x-session-id': session.sessionId,
          ...(server?.token && { 'x-mcp-token': server.token }),
        },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: Date.now(),
          method: 'tools/call',
          params: {
            name: toolName,
            arguments: toolInput,
          },
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      return result.result;
    } catch (error) {
      console.error('Error calling MCP tool:', error);
      throw error;
    }
  };

  // Get all available tools from all connected sessions
  const getAllTools = () => {
    const allTools: Array<MCPTool & { sessionId: string; serverName: string }> = [];
    
    mcpSessions.forEach(session => {
      if (session.status === 'connected') {
        session.tools.forEach(tool => {
          allTools.push({
            ...tool,
            sessionId: session.sessionId,
            serverName: session.serverName,
          });
        });
      }
    });
    
    return allTools;
  };

  // OpenAI chat completion
  const sendMessageOpenAI = async (conversationMessages: Message[]) => {
    if (!aiConfig?.apiKey) {
      throw new Error('OpenAI API key not configured');
    }

    const allTools = getAllTools();
    
    // Convert MCP tools to OpenAI function format
    const functions = allTools.map(tool => ({
      type: 'function' as const,
      function: {
        name: tool.name,
        description: tool.description,
        parameters: tool.inputSchema,
      },
    }));

    const openaiMessages = conversationMessages.map(msg => ({
      role: msg.role,
      content: msg.content,
    }));

    let response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${aiConfig.apiKey}`,
      },
      body: JSON.stringify({
        model: aiConfig.modelName || 'gpt-4o-mini',
        messages: openaiMessages,
        tools: functions.length > 0 ? functions : undefined,
        tool_choice: functions.length > 0 ? 'auto' : undefined,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`OpenAI API error: ${error}`);
    }

    let result = await response.json();
    let assistantMessage = result.choices[0].message;

    // Handle tool calls
    const toolCalls: Array<{ name: string; input: any; result: any }> = [];
    
    while (assistantMessage.tool_calls && assistantMessage.tool_calls.length > 0) {
      console.log('Tool calls:', assistantMessage.tool_calls);

      // Execute all tool calls
      const toolResults = await Promise.all(
        assistantMessage.tool_calls.map(async (toolCall: any) => {
          const toolName = toolCall.function.name;
          const toolInput = JSON.parse(toolCall.function.arguments);
          
          // Find which session has this tool
          const toolInfo = allTools.find(t => t.name === toolName);
          if (!toolInfo) {
            return {
              tool_call_id: toolCall.id,
              role: 'tool',
              name: toolName,
              content: JSON.stringify({ error: 'Tool not found' }),
            };
          }

          const session = mcpSessions.find(s => s.sessionId === toolInfo.sessionId);
          if (!session) {
            return {
              tool_call_id: toolCall.id,
              role: 'tool',
              name: toolName,
              content: JSON.stringify({ error: 'Session not found' }),
            };
          }

          try {
            const result = await callMCPTool(toolName, toolInput, session);
            toolCalls.push({ name: toolName, input: toolInput, result });
            
            return {
              tool_call_id: toolCall.id,
              role: 'tool',
              name: toolName,
              content: JSON.stringify(result),
            };
          } catch (error) {
            return {
              tool_call_id: toolCall.id,
              role: 'tool',
              name: toolName,
              content: JSON.stringify({ error: error instanceof Error ? error.message : 'Unknown error' }),
            };
          }
        })
      );

      // Continue conversation with tool results
      openaiMessages.push(assistantMessage);
      openaiMessages.push(...toolResults);

      response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${aiConfig.apiKey}`,
        },
        body: JSON.stringify({
          model: aiConfig.modelName || 'gpt-4o-mini',
          messages: openaiMessages,
          tools: functions.length > 0 ? functions : undefined,
          tool_choice: functions.length > 0 ? 'auto' : undefined,
        }),
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`OpenAI API error: ${error}`);
      }

      result = await response.json();
      assistantMessage = result.choices[0].message;
    }

    return {
      content: assistantMessage.content,
      toolCalls,
    };
  };

  // Helper function to resolve JSON Schema $ref references
  const resolveSchemaRefs = (schema: any): any => {
    if (!schema || typeof schema !== 'object') {
      return schema;
    }

    // If this object has a $ref, resolve it
    if (schema.$ref && typeof schema.$ref === 'string') {
      const refPath = schema.$ref.split('/');
      if (refPath[0] === '#' && refPath[1] === '$defs') {
        const defName = refPath[2];
        if (schema.$defs && schema.$defs[defName]) {
          // Resolve the reference
          const resolved = resolveSchemaRefs(schema.$defs[defName]);
          // Remove $ref and $defs, keep other properties
          const { $ref, $defs, ...rest } = schema;
          return { ...resolved, ...rest };
        }
      }
    }

    // Recursively resolve refs in the schema
    const result: any = Array.isArray(schema) ? [] : {};
    for (const key in schema) {
      if (key === '$defs') {
        // Skip $defs in the output, but keep for resolution
        continue;
      }
      result[key] = resolveSchemaRefs(schema[key]);
    }

    // If we have $defs at root level, resolve references in properties
    if (schema.$defs && schema.properties) {
      for (const propKey in result.properties) {
        const prop = result.properties[propKey];
        if (prop.$ref && typeof prop.$ref === 'string') {
          const refPath = prop.$ref.split('/');
          if (refPath[0] === '#' && refPath[1] === '$defs') {
            const defName = refPath[2];
            if (schema.$defs[defName]) {
              result.properties[propKey] = resolveSchemaRefs(schema.$defs[defName]);
            }
          }
        }
      }
    }

    return result;
  };

  // Google Gemini chat completion
  const sendMessageGemini = async (conversationMessages: Message[]) => {
    if (!aiConfig?.apiKey) {
      throw new Error('Google API key not configured');
    }

    const allTools = getAllTools();

    // Convert MCP tools to Gemini function format
    // Gemini doesn't support $defs and $ref, so we need to resolve them
    const functionDeclarations = allTools.map(tool => ({
      name: tool.name,
      description: tool.description,
      parameters: resolveSchemaRefs(tool.inputSchema),
    }));

    // Convert messages to Gemini format
    const contents = conversationMessages.map(msg => ({
      role: msg.role === 'assistant' ? 'model' : 'user',
      parts: [{ text: msg.content }],
    }));

    const requestBody: any = {
      contents,
    };

    if (functionDeclarations.length > 0) {
      requestBody.tools = [{ functionDeclarations }];
    }

    let response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${aiConfig.modelName || 'gemini-2.0-flash-exp'}:generateContent?key=${aiConfig.apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      }
    );

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Gemini API error: ${error}`);
    }

    let result = await response.json();
    let candidate = result.candidates[0];

    const toolCalls: Array<{ name: string; input: any; result: any }> = [];

    // Handle function calls
    while (
      candidate.content.parts &&
      candidate.content.parts.some((part: any) => part.functionCall)
    ) {
      console.log('Function calls:', candidate.content.parts);

      // Execute all function calls
      const functionResponses = await Promise.all(
        candidate.content.parts
          .filter((part: any) => part.functionCall)
          .map(async (part: any) => {
            const functionCall = part.functionCall;
            const toolName = functionCall.name;
            const toolInput = functionCall.args;

            // Find which session has this tool
            const toolInfo = allTools.find(t => t.name === toolName);
            if (!toolInfo) {
              return {
                functionResponse: {
                  name: toolName,
                  response: { error: 'Tool not found' },
                },
              };
            }

            const session = mcpSessions.find(s => s.sessionId === toolInfo.sessionId);
            if (!session) {
              return {
                functionResponse: {
                  name: toolName,
                  response: { error: 'Session not found' },
                },
              };
            }

            try {
              const result = await callMCPTool(toolName, toolInput, session);
              toolCalls.push({ name: toolName, input: toolInput, result });
              
              return {
                functionResponse: {
                  name: toolName,
                  response: result,
                },
              };
            } catch (error) {
              return {
                functionResponse: {
                  name: toolName,
                  response: { error: error instanceof Error ? error.message : 'Unknown error' },
                },
              };
            }
          })
      );

      // Continue conversation with function responses
      contents.push(candidate.content);
      contents.push({
        role: 'user',
        parts: functionResponses,
      });

      const continueRequestBody: any = {
        contents,
      };

      if (functionDeclarations.length > 0) {
        continueRequestBody.tools = [{ functionDeclarations }];
      }

      response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${aiConfig.modelName || 'gemini-2.0-flash-exp'}:generateContent?key=${aiConfig.apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(continueRequestBody),
        }
      );

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`Gemini API error: ${error}`);
      }

      result = await response.json();
      candidate = result.candidates[0];
    }

    const textPart = candidate.content.parts.find((part: any) => part.text);
    return {
      content: textPart?.text || '',
      toolCalls,
    };
  };

  // Handle sending message
  const handleSendMessage = async () => {
    if (!input.trim() || loading) return;

    if (!aiConfig || !aiConfig.apiKey) {
      alert('Please configure AI settings first');
      setShowSettings(true);
      return;
    }

    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const conversationMessages = [...messages, userMessage];

      let result;
      if (aiConfig.provider === 'openai' || aiConfig.provider === 'azure') {
        result = await sendMessageOpenAI(conversationMessages);
      } else if (aiConfig.provider === 'google') {
        result = await sendMessageGemini(conversationMessages);
      } else {
        throw new Error('Unsupported AI provider');
      }

      const assistantMessage: Message = {
        id: `msg-${Date.now()}`,
        role: 'assistant',
        content: result.content,
        timestamp: new Date(),
        toolCalls: result.toolCalls.length > 0 ? result.toolCalls : undefined,
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage: Message = {
        id: `msg-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Save AI config callback
  const handleSaveAIConfig = (newConfig: AIProviderConfig) => {
    setAiConfig(newConfig);
    localStorage.setItem('mcp-agent-ai-config', JSON.stringify(newConfig));
  };

  // Save MCP servers callback
  const handleSaveMCPServers = (newServers: MCPServerConfig[]) => {
    setMcpServers(newServers);
    localStorage.setItem('mcp-agent-mcp-servers', JSON.stringify(newServers));

    // Disconnect all current sessions
    setMcpSessions([]);

    // Connect to enabled servers
    newServers.filter(s => s.enabled).forEach(server => {
      connectToMCP(server);
    });
  };

  return (
    <div className="flex flex-col h-screen bg-wso2-gray-50 dark:bg-wso2-dark-bg">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 card-wso2 border-b border-wso2-gray-200 dark:border-wso2-dark-border rounded-none">
        <div className="flex items-center gap-4">
          <WSO2ProductLogo productName="MCP AI Agent" size="md" />
          
          {/* MCP Server Status */}
          {mcpSessions.length > 0 && (
            <div className="flex gap-2">
              {mcpSessions.map(session => (
                <div
                  key={session.sessionId}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-wso2 bg-wso2-gray-100 dark:bg-wso2-dark-surface text-xs border border-wso2-gray-200 dark:border-wso2-dark-border"
                  title={session.error || session.status}
                >
                  <div
                    className={`w-2 h-2 rounded-full ${
                      session.status === 'connected'
                        ? 'bg-wso2-success-500'
                        : session.status === 'error'
                        ? 'bg-wso2-error-500'
                        : 'bg-wso2-warning-500'
                    }`}
                  />
                  <span className="text-wso2-gray-700 dark:text-wso2-gray-300 font-medium">
                    {session.serverName}
                  </span>
                  {session.status === 'connected' && (
                    <span className="text-wso2-gray-500 dark:text-wso2-gray-400">
                      ({session.tools.length} tools)
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowSettings(true)}
            className="p-2.5 rounded-wso2 hover:bg-wso2-gray-100 dark:hover:bg-wso2-dark-surface transition-colors border border-wso2-gray-200 dark:border-wso2-dark-border"
            title="Settings"
          >
            <svg
              className="w-5 h-5 text-wso2-gray-700 dark:text-wso2-gray-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
          </button>
          <ThemeToggle />
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-wso2-gray-50 dark:bg-wso2-dark-bg">
        <div className="max-w-4xl mx-auto px-6 py-8">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="mb-8">
                <div className="w-20 h-20 bg-gradient-to-br from-wso2-primary-500 to-wso2-primary-600 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-wso2-lg">
                  <svg
                    className="w-10 h-10 text-white"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423L16.5 15.75l.394 1.183a2.25 2.25 0 001.423 1.423L19.5 18.75l-1.183.394a2.25 2.25 0 00-1.423 1.423z"
                    />
                  </svg>
                </div>
                <h2 className="text-3xl font-bold text-wso2-gray-900 dark:text-white mb-3">
                  Welcome to WSO2 MCP AI Agent
                </h2>
                <p className="text-lg text-wso2-gray-600 dark:text-wso2-gray-400 mb-6 max-w-md">
                  Connect to MCP servers and chat with AI assistants using WSO2's powerful integration platform
                </p>
              </div>

              {(!aiConfig || !aiConfig.apiKey) && (
                <button
                  onClick={() => setShowSettings(true)}
                  className="btn-wso2-primary px-8 py-3 text-base font-semibold shadow-wso2-md hover:shadow-wso2-lg flex items-center"
                >
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  Configure Settings
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map(message => (
                <div
                  key={message.id}
                  className={`flex ${
                    message.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <div className={`flex items-start space-x-3 max-w-[85%] ${
                    message.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''
                  }`}>
                    {/* Avatar */}
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                      message.role === 'user'
                        ? 'bg-wso2-gray-600 dark:bg-wso2-gray-400'
                        : 'bg-gradient-to-br from-wso2-primary-500 to-wso2-primary-600'
                    }`}>
                      <span className="text-white text-sm font-medium">
                        {message.role === 'user' ? 'U' : 'AI'}
                      </span>
                    </div>

                    {/* Message */}
                    <div
                      className={`px-4 py-3 rounded-wso2 shadow-wso2-sm ${
                        message.role === 'user'
                          ? 'bg-wso2-primary-500 text-white'
                          : 'card-wso2 text-wso2-gray-900 dark:text-white'
                      }`}
                    >
                      <div className="whitespace-pre-wrap break-words leading-relaxed">
                        {message.content}
                      </div>

                      {message.toolCalls && message.toolCalls.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-wso2-gray-200 dark:border-wso2-dark-border">
                          <div className="text-sm font-medium mb-3 text-wso2-gray-700 dark:text-wso2-gray-300">
                            🔧 Tool Calls:
                          </div>
                          {message.toolCalls.map((call, idx) => (
                            <div
                              key={idx}
                              className="text-xs mb-3 p-3 rounded-wso2 bg-wso2-gray-50 dark:bg-wso2-dark-surface border border-wso2-gray-200 dark:border-wso2-dark-border"
                            >
                              <div className="font-semibold text-wso2-primary-600 dark:text-wso2-primary-400 mb-1">
                                {call.name}
                              </div>
                              <div className="text-wso2-gray-600 dark:text-wso2-gray-400 mb-1">
                                <span className="font-medium">Input:</span> {JSON.stringify(call.input)}
                              </div>
                              {call.result && (
                                <div className="text-wso2-gray-600 dark:text-wso2-gray-400">
                                  <span className="font-medium">Result:</span> {JSON.stringify(call.result)}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-wso2-gray-200 dark:border-wso2-dark-border bg-white dark:bg-wso2-dark-surface">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="relative flex items-end gap-3">
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Type your message to the AI agent..."
                rows={1}
                disabled={loading}
                className="w-full resize-none rounded-wso2 border border-wso2-gray-300 dark:border-wso2-dark-border bg-white dark:bg-wso2-dark-surface px-4 py-3 pr-12 text-wso2-gray-900 dark:text-white placeholder-wso2-gray-500 dark:placeholder-wso2-gray-400 focus:outline-none focus:ring-2 focus:ring-wso2-primary-500 focus:border-transparent disabled:opacity-50 min-h-[52px] max-h-[200px] transition-colors duration-200"
              />
              {/* Send icon in input */}
              <button
                onClick={handleSendMessage}
                disabled={loading || !input.trim()}
                className="absolute right-2 top-1/2 transform -translate-y-1/2 p-2 text-wso2-primary-500 hover:text-wso2-primary-600 disabled:text-wso2-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
            <button
              onClick={handleSendMessage}
              disabled={loading || !input.trim()}
              className="btn-wso2-primary px-6 py-3 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 min-h-[52px]"
            >
              {loading ? (
                <>
                  <svg
                    className="animate-spin h-5 w-5"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    ></circle>
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    ></path>
                  </svg>
                  <span>Sending...</span>
                </>
              ) : (
                <>
                  <span>Send</span>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </>
              )}
            </button>
          </div>

          {(!aiConfig || !aiConfig.apiKey) && (
            <div className="mt-3 p-3 bg-wso2-warning-50 dark:bg-wso2-warning-950/20 border border-wso2-warning-200 dark:border-wso2-warning-800 rounded-wso2 flex items-center space-x-2">
              <svg className="w-5 h-5 text-wso2-warning-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.464 0L4.34 15.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              <span className="text-sm text-wso2-warning-700 dark:text-wso2-warning-300 font-medium">
                Please configure AI settings to start chatting
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <WSO2Footer />

      {/* Settings Modal */}
      {showSettings && (
        <SettingsModal
          isOpen={showSettings}
          onClose={() => setShowSettings(false)}
          aiConfig={aiConfig}
          mcpServers={mcpServers}
          onSaveAIConfig={handleSaveAIConfig}
          onSaveMCPServers={handleSaveMCPServers}
        />
      )}
    </div>
  );
}

