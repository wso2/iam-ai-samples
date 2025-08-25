import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MessageCircle, X, Send, Paperclip, Maximize2, Minimize2 } from 'lucide-react';

interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

interface ConsentRequest {
  id: string;
  content: string;
  options: {
    accept: string;
    reject: string;
  };
}

interface AuthRequest {
  state: string;
  auth_url: string;
  context?: Record<string, any>;
}

const ChatComponent: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [pendingConsent, setPendingConsent] = useState<ConsentRequest | null>(null);
  const [pendingAuth, setPendingAuth] = useState<AuthRequest | null>(null);
  const [authorizationCompleted, setAuthorizationCompleted] = useState(false);
  
  const ws = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const sessionId = useRef<string>('');

  // Generate session ID
  const generateSessionId = () => {
    return 'session_' + Math.random().toString(36).substring(2, 15);
  };

  // Add message helpers
  const addMessage = useCallback((type: Message['type'], content: string, id?: string) => {
    const message: Message = {
      id: id || Date.now().toString(),
      type,
      content,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, message]);
  }, []);

  const addUserMessage = useCallback((content: string) => addMessage('user', content), [addMessage]);
  const addAssistantMessage = useCallback((content: string, id?: string) => addMessage('assistant', content, id), [addMessage]);
  const addSystemMessage = useCallback((content: string) => addMessage('system', content), [addMessage]);

  // Initialize WebSocket connection
  const connectWebSocket = useCallback(() => {
    if (!sessionId.current) {
      sessionId.current = generateSessionId();
    }

    // WebSocket URL for AI agent backend
    const wsUrl = `${process.env.REACT_APP_AGENT_URL}/chat?session_id=${sessionId.current}`;
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setIsConnected(true);
      console.log('WebSocket connected');
    };

    ws.current.onmessage = (event) => {
      setIsTyping(false);
      
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'message') {
          addAssistantMessage(data.content, data.messageId);
        } else if (data.type === 'consent_request') {
          setPendingConsent({
            id: data.messageId,
            content: data.content,
            options: data.consentOptions || { accept: 'Accept', reject: 'Reject' }
          });
        } else if (data.type === 'auth_request') {
          setPendingAuth({
            state: data.state,
            auth_url: data.auth_url,
            context: data.context
          });
        }
      } catch (error) {
        // Handle plain text messages
        addAssistantMessage(event.data);
      }
    };

    ws.current.onclose = () => {
      setIsConnected(false);
      setIsTyping(false);
      console.log('WebSocket disconnected');
    };

    ws.current.onerror = (error) => {
      setIsConnected(false);
      setIsTyping(false);
      console.error('WebSocket error:', error);
    };
  }, [addAssistantMessage]);

  // Listen for OAuth callback messages
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data && event.data.type === 'auth_callback' && event.data.state) {
        setAuthorizationCompleted(true);
        addSystemMessage('Authorization completed successfully. Processing your booking...');
        setPendingAuth(null);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [addSystemMessage]);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  // Handle sending messages to backend
  const handleSendMessage = useCallback(async () => {
    if (!inputValue.trim()) return;

    // If WebSocket is not connected, try to connect first
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
      if (!isConnected) {
        connectWebSocket();
        // Wait a moment for connection
        setTimeout(() => {
          if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            sendMessageToBackend();
          } else {
            // Fallback to local response if backend is unavailable
            handleLocalFallback();
          }
        }, 1000);
        return;
      }
    }

    sendMessageToBackend();
  }, [inputValue, isConnected, connectWebSocket]);

  const sendMessageToBackend = () => {
    if (!inputValue.trim() || !ws.current || ws.current.readyState !== WebSocket.OPEN) return;

    addUserMessage(inputValue);
    setIsTyping(true);

    const jsonMsg = {
      type: 'user_message',
      content: inputValue,
      sessionId: sessionId.current
    };

    ws.current.send(JSON.stringify(jsonMsg));
    setInputValue('');
  };

  // Fallback to local responses if backend is unavailable
  const handleLocalFallback = () => {
    const userMessage = inputValue.trim();
    addUserMessage(userMessage);
    setInputValue('');
    setIsTyping(true);
  };

  // Handle consent response
  const handleConsentResponse = (decision: 'accept' | 'reject') => {
    if (!pendingConsent) return;

    const responseText = decision === 'accept' ? pendingConsent.options.accept : pendingConsent.options.reject;
    addUserMessage(responseText);

    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const response = {
        type: 'consent_response',
        decision,
        messageId: pendingConsent.id,
        sessionId: sessionId.current
      };
      ws.current.send(JSON.stringify(response));
    }

    setPendingConsent(null);
  };

  // Handle authorization
  const handleAuthorization = () => {
    if (!pendingAuth) return;

    setAuthorizationCompleted(false);
    addSystemMessage('Authorization window opened. Please complete the login process.');

    const authWindow = window.open(
      pendingAuth.auth_url,
      'OAuthWindow',
      'width=600,height=700,left=200,top=100'
    );

    if (!authWindow) {
      addSystemMessage('Popup was blocked. Please allow popups for this site.');
      return;
    }

    const checkClosed = setInterval(() => {
      if (authWindow.closed) {
        clearInterval(checkClosed);
        setTimeout(() => {
          if (pendingAuth && !authorizationCompleted) {
            addSystemMessage('Authorization window was closed. The booking was not completed.');
            setPendingAuth(null);
          }
        }, 500);
      }
    }, 1000);
  };

  // Initialize connection when chat opens
  useEffect(() => {
    if (isOpen && !ws.current) {
      connectWebSocket();
    }
  }, [isOpen, connectWebSocket]);

  // Handle key press
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Format timestamp
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: false 
    });
  };

  // Enhanced markdown renderer
  const renderContent = (content: string) => {
    // Basic markdown parsing
    let html = content
      // Bold text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      // Italic text
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      // Inline code
      .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 rounded text-sm">$1</code>')
      // Code blocks
      .replace(/```([\s\S]*?)```/g, '<pre class="bg-gray-100 p-2 rounded mt-2"><code>$1</code></pre>')
      // Line breaks
      .replace(/\n/g, '<br />');
    
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <>
      {/* Chat Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 bg-blue-600 hover:bg-blue-700 text-white rounded-full p-4 shadow-lg transition-all duration-300 hover:scale-110"
        >
          <MessageCircle className="h-6 w-6" />
        </button>
      )}

      {/* Chat Panel */}
      {isOpen && (
        <>
          {/* Backdrop for maximized mode */}
          {isMaximized && (
            <div className="fixed inset-0 bg-black bg-opacity-50 z-40" />
          )}
          
          {/* Chat Container */}
          <div className={`fixed z-50 bg-white shadow-2xl transition-all duration-300 flex flex-col ${
            isMaximized 
              ? 'inset-6 rounded-lg' 
              : 'bottom-4 right-6 w-1/3 min-w-[400px] max-w-[500px] rounded-lg'
          }`}
          style={{
            height: 'calc(100vh - 48px)',
            maxHeight: 'calc(100vh - 48px)'
          }}>
            
            {/* Header */}
            <div className="bg-blue-600 text-white p-4 flex items-center justify-between rounded-t-lg flex-shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-white bg-opacity-20 rounded-full flex items-center justify-center text-sm font-bold text-white">
                  GA
                </div>
                <div>
                  <div className="font-semibold">Gardeo Assistant</div>
                  <div className="flex items-center gap-2 text-xs text-blue-200">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'}`}></div>
                    <span>{isConnected ? 'AI Assistant Online' : 'Connecting...'}</span>
                  </div>
                </div>
              </div>

              {/* Header Controls */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsMaximized(!isMaximized)}
                  className="p-1.5 hover:bg-blue-500 rounded transition-colors"
                  title={isMaximized ? 'Minimize' : 'Maximize'}
                >
                  {isMaximized ? (
                    <Minimize2 className="h-4 w-4" />
                  ) : (
                    <Maximize2 className="h-4 w-4" />
                  )}
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  className="p-1.5 hover:bg-blue-500 rounded transition-colors"
                  title="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Chat Content */}
            <div className="flex flex-col flex-1 min-h-0">
              {/* Messages Area */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
                {/* Messages */}
                {messages.map((message) => (
                  <div key={message.id} className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] ${message.type === 'user' ? 'order-2' : 'order-1'}`}>
                      <div className={`px-4 py-3 rounded-2xl ${
                        message.type === 'user'
                          ? 'bg-blue-600 text-white ml-auto'
                          : message.type === 'system'
                          ? 'bg-blue-50 text-blue-800 italic text-center border border-blue-200'
                          : 'bg-white text-gray-900 border border-gray-200'
                      }`}>
                        {message.type === 'assistant' ? (
                          <div className="prose prose-sm max-w-none">
                            {renderContent(message.content)}
                          </div>
                        ) : (
                          <p className="whitespace-pre-wrap">{message.content}</p>
                        )}
                      </div>
                      <div className={`text-xs mt-1 px-2 ${
                        message.type === 'user' ? 'text-right text-gray-500' : 'text-left text-gray-500'
                      }`}>
                        {formatTime(message.timestamp)}
                      </div>
                    </div>
                  </div>
                ))}

                {/* Consent Request */}
                {pendingConsent && (
                  <div className="bg-white border border-gray-200 rounded-lg p-4">
                    <p className="mb-3 text-sm text-gray-700">{pendingConsent.content}</p>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <button
                        onClick={() => handleConsentResponse('accept')}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors text-sm"
                      >
                        {pendingConsent.options.accept}
                      </button>
                      <button
                        onClick={() => handleConsentResponse('reject')}
                        className="bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-lg font-medium transition-colors text-sm"
                      >
                        {pendingConsent.options.reject}
                      </button>
                    </div>
                  </div>
                )}

                {/* Auth Request */}
                {pendingAuth && (
                  <div className="bg-white border border-gray-200 rounded-lg p-4">
                    <h4 className="font-semibold mb-2 text-sm text-gray-900">Approval needed!</h4>
                    <p className="text-gray-600 mb-3 text-sm">To complete your hotel booking, please approve and login to your account.</p>
                    {pendingAuth.context && (
                      <div className="mb-3 text-sm bg-gray-50 p-2 rounded-lg">
                        <strong className="text-gray-900">Booking Details:</strong>
                        {Object.entries(pendingAuth.context).map(([key, value]) => (
                          <div key={key} className="text-gray-600 text-xs">
                            {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: {String(value)}
                          </div>
                        ))}
                      </div>
                    )}
                    <button
                      onClick={handleAuthorization}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors text-sm w-full sm:w-auto"
                    >
                      Approve
                    </button>
                  </div>
                )}

                {/* Typing Indicator */}
                {isTyping && (
                  <div className="flex justify-start">
                    <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3 flex items-center gap-1">
                      <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Input Area */}
              <div className="p-4 border-t border-gray-200 bg-white flex-shrink-0 rounded-b-lg">
                <div className="flex items-center gap-2">
                  <input
                    ref={inputRef}
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder="Ask me about rooms, amenities, or bookings..."
                    className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    disabled={!isConnected && ws.current?.readyState !== WebSocket.CONNECTING}
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={!inputValue.trim()}
                    className="p-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Send className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
};

export default ChatComponent;
