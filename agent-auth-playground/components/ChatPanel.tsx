/**
 * Copyright (c) 2026, WSO2 LLC. (https://www.wso2.com).
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
'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import { ChatMessage } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ChatPanelProps {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  onSendMessage: (message: string) => void;
  onClear: () => void;
  disabled?: boolean;
  oboConsentPending?: boolean;
  hasTrace?: boolean;
  onViewAuthFlow?: () => void;
  onHide?: () => void;
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-1 last:mb-0 break-words">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        ul: ({ children }) => <ul className="list-disc pl-4 mb-1 space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 mb-1 space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="text-sm">{children}</li>,
        pre: ({ children }) => (
          <pre className="bg-slate-800 text-slate-100 rounded-lg p-3 text-xs font-mono overflow-x-auto my-2 whitespace-pre-wrap">
            {children}
          </pre>
        ),
        code: ({ children, className }) => (
          <code
            className={
              className
                ? 'text-inherit font-mono text-xs'
                : 'bg-gray-200 text-gray-800 px-1 py-0.5 rounded text-xs font-mono'
            }
          >
            {children}
          </code>
        ),
        h1: ({ children }) => <h1 className="text-base font-bold mb-1 mt-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-bold mb-1 mt-2">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mb-1 mt-1">{children}</h3>,
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="underline text-blue-600 hover:text-blue-800">
            {children}
          </a>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-gray-400 pl-2 italic my-1 text-gray-600">
            {children}
          </blockquote>
        ),
        hr: () => <hr className="border-gray-300 my-2" />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default function ChatPanel({
  messages,
  isLoading,
  error,
  onSendMessage,
  onClear,
  disabled = false,
  oboConsentPending = false,
  hasTrace = false,
  onViewAuthFlow,
  onHide,
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ID of the most recent obo-consent message — only that button stays active while consent is pending
  const lastConsentMsgId = useMemo(() => {
    const consentMsgs = messages.filter((m) => m.type === 'obo-consent');
    return consentMsgs.length > 0 ? consentMsgs[consentMsgs.length - 1].id : null;
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || disabled || oboConsentPending) return;
    onSendMessage(input);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200">
      {/* Header */}
      <div className="border-b border-gray-200 p-3 flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-gray-900">Chat</h3>
          <p className="text-xs text-gray-500">Test your workflow</p>
        </div>
        <div className="flex items-center gap-1.5">
          {onViewAuthFlow && (
            <button
              onClick={hasTrace ? onViewAuthFlow : undefined}
              disabled={!hasTrace}
              className={`px-3 py-1.5 text-xs font-medium border rounded-md transition-colors ${
                hasTrace
                  ? 'text-cyan-700 bg-cyan-50 hover:bg-cyan-100 border-cyan-200 cursor-pointer'
                  : 'text-gray-400 bg-gray-50 border-gray-200 cursor-not-allowed'
              }`}
            >
              View Auth Flow
            </button>
          )}
          {onHide && (
            <button
              onClick={onHide}
              aria-label="Hide chat"
              title="Hide chat"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-900 transition-colors"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-4 w-4"
              >
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-center text-gray-500">
            <div>
              <p className="text-sm font-semibold mb-2">No messages yet</p>
              <p className="text-xs">Send a message to test your workflow</p>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                  msg.role === 'user'
                    ? 'bg-blue-500 text-white'
                    : msg.type === 'obo-consent'
                    ? 'bg-amber-50 text-gray-900 border border-amber-200'
                    : 'bg-gray-100 text-gray-900'
                }`}
              >
                {msg.type === 'obo-consent' && msg.metadata?.authUrl ? (
                  <>
                    <p className="text-sm font-semibold text-amber-800 mb-1">
                      Authorization Required
                    </p>
                    <p className="text-xs text-gray-700 mb-3 whitespace-pre-wrap">
                      {msg.content.replace(/^Authorization Required[^\n]*\n\n/, '')}
                    </p>
                    {(() => {
                      const isActive = oboConsentPending && msg.id === lastConsentMsgId;
                      return isActive ? (
                        <button
                          onClick={() =>
                            window.open(
                              msg.metadata?.authUrl ?? '',
                              'obo-auth-popup',
                              'width=520,height=680,scrollbars=yes,resizable=yes,left=' +
                                Math.round(window.screenX + (window.outerWidth - 520) / 2) +
                                ',top=' +
                                Math.round(window.screenY + (window.outerHeight - 680) / 2)
                            )
                          }
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors cursor-pointer"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clipRule="evenodd" />
                          </svg>
                          Authorize
                        </button>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-400 bg-gray-100 border border-gray-200 rounded-md cursor-not-allowed select-none">
                          <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clipRule="evenodd" />
                          </svg>
                          Authorized
                        </span>
                      );
                    })()}
                  </>
                ) : msg.role === 'assistant' ? (
                  <div className="text-sm">
                    <MarkdownContent content={msg.content} />
                  </div>
                ) : (
                  <p className="text-sm break-words">{msg.content}</p>
                )}
                <p
                  className={`text-xs mt-1 ${
                    msg.role === 'user' ? 'text-blue-100' : 'text-gray-500'
                  }`}
                >
                  {new Date(msg.timestamp).toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))
        )}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 text-gray-900 px-4 py-2 rounded-lg">
              <div className="flex items-center gap-2">
                <Spinner className="w-4 h-4" />
                <span className="text-sm">
                  {oboConsentPending ? 'Exchanging token...' : 'Thinking...'}
                </span>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex justify-start">
            <div className="bg-red-50 text-red-700 border border-red-200 px-4 py-2 rounded-lg max-w-xs">
              <p className="text-sm font-semibold">Error</p>
              <p className="text-sm mt-1">{error}</p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* OBO consent banner */}
      {oboConsentPending && (
        <div className="mx-4 mb-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-md">
          <p className="text-xs text-amber-800 font-medium">
            Waiting for authorization...
          </p>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-gray-200 p-3 space-y-2">
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            disabled={disabled || isLoading || oboConsentPending}
            className="flex-1"
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || disabled || isLoading || oboConsentPending}
            size="sm"
          >
            {isLoading ? <Spinner className="w-4 h-4" /> : 'Send'}
          </Button>
        </div>

        {messages.length > 0 && (
          <Button
            onClick={onClear}
            variant="ghost"
            size="sm"
            disabled={disabled && !oboConsentPending}
            className="w-full text-xs"
          >
            Clear Chat
          </Button>
        )}
      </div>
    </div>
  );
}
