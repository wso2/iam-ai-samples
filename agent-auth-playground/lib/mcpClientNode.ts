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
import 'server-only';

import {
  Client,
  StreamableHTTPClientTransport,
} from '@modelcontextprotocol/client';

export interface MCPDiscoveredTool {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

export interface MCPToolCallResult {
  isError: boolean;
  content: string;
  structuredContent?: Record<string, unknown>;
  raw: unknown;
}

type MCPTransport = StreamableHTTPClientTransport;

const DEFAULT_RECONNECTION_OPTIONS = {
  initialReconnectionDelay: 1_000,
  maxReconnectionDelay: 10_000,
  reconnectionDelayGrowFactor: 1.5,
  maxRetries: 2,
};

export class MCPClientNodeRuntime {
  private client: Client | null = null;
  private transport: MCPTransport | null = null;
  private endpoint: string | null = null;
  private toolsCache: MCPDiscoveredTool[] = [];
  private accessToken: string | null = null;

  constructor(private readonly maxReconnectAttempts: number = 2) {}

  setAccessToken(token: string): void {
    this.accessToken = token;
  }

  async connect(
    endpoint: string,
    options?: { cachedTools?: MCPDiscoveredTool[]; skipDiscovery?: boolean }
  ): Promise<void> {
    const normalizedEndpoint = endpoint.trim();

    if (!normalizedEndpoint) {
      throw new Error('MCP server endpoint is required.');
    }

    if (this.client && this.endpoint === normalizedEndpoint) {
      if (options?.cachedTools && this.toolsCache.length === 0) {
        this.toolsCache = options.cachedTools;
      }
      return;
    }

    let url: URL;
    try {
      url = new URL(normalizedEndpoint);
    } catch {
      throw new Error(`Invalid MCP server endpoint: ${normalizedEndpoint}`);
    }

    await this.disconnect();

    const token = this.accessToken;
    const transportFactories: Array<() => MCPTransport> = [
      () =>
        new StreamableHTTPClientTransport(url, {
          reconnectionOptions: DEFAULT_RECONNECTION_OPTIONS,
          ...(token ? { authProvider: { token: async () => token } } : {}),
        }),
    ];

    let lastError: unknown;

    for (const createTransport of transportFactories) {
      const client = new Client({
        name: 'agent-auth-playground-mcp-client',
        version: '1.0.0',
      });
      const transport = createTransport();

      try {
        await client.connect(transport);

        this.client = client;
        this.transport = transport;
        this.endpoint = normalizedEndpoint;

        if (options?.cachedTools) {
          this.toolsCache = options.cachedTools;
        } else if (options?.skipDiscovery) {
          this.toolsCache = [];
        } else {
          this.toolsCache = await this.fetchTools(client);
        }
        return;
      } catch (error) {
        lastError = error;
        await transport.close().catch(() => undefined);
      }
    }

    throw new Error(
      `Unable to connect to MCP server at ${normalizedEndpoint}: ${this.formatError(lastError)}`
    );
  }

  async disconnect(): Promise<void> {
    this.client = null;
    this.toolsCache = [];

    const activeTransport = this.transport;
    this.transport = null;

    if (!activeTransport) {
      return;
    }

    await activeTransport.close().catch(() => undefined);
  }

  async listTools(): Promise<MCPDiscoveredTool[]> {
    return this.executeWithReconnect(async (client) => {
      if (this.toolsCache.length === 0) {
        this.toolsCache = await this.fetchTools(client);
      }

      return this.toolsCache;
    });
  }

  async callTool(
    name: string,
    args: Record<string, unknown> = {}
  ): Promise<MCPToolCallResult> {
    return this.executeWithReconnect(async (client) => {
      const result = await client.callTool({
        name,
        arguments: args,
      });

      return {
        isError: Boolean(result.isError),
        content: this.formatContent(result.content as Array<Record<string, unknown>>),
        structuredContent: result.structuredContent,
        raw: result,
      };
    });
  }

  private async executeWithReconnect<T>(
    operation: (client: Client) => Promise<T>
  ): Promise<T> {
    let lastError: unknown;

    for (let attempt = 0; attempt <= this.maxReconnectAttempts; attempt += 1) {
      try {
        if (!this.client) {
          if (!this.endpoint) {
            throw new Error('MCP client is not connected.');
          }

          await this.connect(this.endpoint);
        }

        if (!this.client) {
          throw new Error('MCP client is not connected.');
        }

        return await operation(this.client);
      } catch (error) {
        lastError = error;

        if (attempt >= this.maxReconnectAttempts || !this.endpoint) {
          break;
        }

        await this.reconnect();
      }
    }

    throw new Error(`MCP operation failed: ${this.formatError(lastError)}`);
  }

  private async reconnect(): Promise<void> {
    if (!this.endpoint) {
      throw new Error('Cannot reconnect MCP client without an endpoint.');
    }

    const preservedTools = this.toolsCache.length > 0 ? [...this.toolsCache] : undefined;
    await this.connect(this.endpoint, preservedTools ? { cachedTools: preservedTools } : undefined);
  }

  private async fetchTools(client: Client): Promise<MCPDiscoveredTool[]> {
    const tools: MCPDiscoveredTool[] = [];
    let cursor: string | undefined;

    do {
      const page = await client.listTools(cursor ? { cursor } : undefined);

      for (const tool of page.tools) {
        tools.push({
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema as Record<string, unknown>,
          outputSchema: tool.outputSchema as Record<string, unknown> | undefined,
        });
      }

      cursor = page.nextCursor;
    } while (cursor);

    return tools;
  }

  private formatContent(content: Array<Record<string, unknown>>): string {
    if (!Array.isArray(content) || content.length === 0) {
      return '';
    }

    const formattedParts = content
      .map((part) => {
        const type = this.getString(part.type);

        if (type === 'text') {
          return this.getString(part.text) || '';
        }

        if (type === 'resource_link') {
          const name = this.getString(part.name) || 'resource';
          const uri = this.getString(part.uri) || 'unknown';
          return `[resource link] ${name}: ${uri}`;
        }

        if (type === 'resource') {
          const resource = part.resource;
          if (resource && typeof resource === 'object') {
            const asRecord = resource as Record<string, unknown>;
            const uri = this.getString(asRecord.uri) || 'unknown';
            const text = this.getString(asRecord.text);
            if (text) {
              return `[resource] ${uri}\n${text}`;
            }
            return `[resource] ${uri}`;
          }
        }

        if (type === 'image') {
          const mimeType = this.getString(part.mimeType) || 'image';
          return `[image content] ${mimeType}`;
        }

        if (type === 'audio') {
          const mimeType = this.getString(part.mimeType) || 'audio';
          return `[audio content] ${mimeType}`;
        }

        return JSON.stringify(part);
      })
      .filter((value) => value.length > 0);

    return formattedParts.join('\n');
  }

  private getString(value: unknown): string | null {
    return typeof value === 'string' ? value : null;
  }

  private formatError(error: unknown): string {
    if (error instanceof Error) {
      return error.message;
    }

    if (typeof error === 'string') {
      return error;
    }

    return 'Unknown error';
  }
}
