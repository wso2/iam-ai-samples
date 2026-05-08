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
import { ChatGoogleGenerativeAI } from '@langchain/google-genai';
import { ChatOpenAI } from '@langchain/openai';
import { ChatAnthropic } from '@langchain/anthropic';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';

export type ProviderName = 'gemini' | 'openai' | 'anthropic' | 'azure-openai';

export const PROVIDER_MODELS: Record<ProviderName, string[]> = {
  gemini: [
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
    'gemini-2.5-pro',
    'gemini-3-flash-preview',
    'gemini-3.1-flash-lite-preview',
    'gemini-3.1-pro-preview',
  ],
  openai: ['gpt-4o', 'gpt-4-turbo', 'gpt-3.5-turbo'],
  anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'],
  'azure-openai': [],
};

async function invokeVertexAI(
  gcpAccessToken: string,
  gcpProjectId: string,
  model: string,
  message: string,
  systemPrompt: string,
  temperature: number,
  maxTokens: number
): Promise<string> {
  const location = 'us-central1';
  const url = `https://${location}-aiplatform.googleapis.com/v1/projects/${gcpProjectId}/locations/${location}/publishers/google/models/${model}:generateContent`;

  const body = {
    contents: [{ role: 'user', parts: [{ text: message }] }],
    ...(systemPrompt && {
      systemInstruction: { parts: [{ text: systemPrompt }] },
    }),
    generationConfig: { temperature, maxOutputTokens: maxTokens },
  };

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${gcpAccessToken}`,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Vertex AI error ${response.status}: ${err}`);
  }

  const data = await response.json();
  return data?.candidates?.[0]?.content?.parts?.[0]?.text ?? '';
}

async function invokeAzureOpenAI(
  resourceName: string,
  deploymentName: string,
  apiVersion: string,
  apiKey: string,
  message: string,
  systemPrompt: string,
  maxTokens: number
): Promise<string> {
  const url = `https://${resourceName}.openai.azure.com/openai/deployments/${deploymentName}/chat/completions?api-version=${apiVersion}`;

  const messages: Array<{ role: string; content: string }> = [];
  if (systemPrompt) {
    messages.push({ role: 'system', content: systemPrompt });
  }
  messages.push({ role: 'user', content: message });

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'api-key': apiKey,
    },
    body: JSON.stringify({ messages, max_completion_tokens: maxTokens }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Azure OpenAI error ${response.status}: ${err}`);
  }

  const data = await response.json();
  return data?.choices?.[0]?.message?.content ?? '';
}

export async function invokeLLM(
  provider: ProviderName,
  apiKey: string,
  model: string,
  message: string,
  systemPrompt: string,
  temperature: number,
  maxTokens: number,
  gcpAccessToken?: string,
  gcpProjectId?: string,
  azureResourceName?: string,
  azureDeploymentName?: string,
  azureApiVersion?: string
): Promise<string> {

  if (provider === 'azure-openai') {
    if (!azureResourceName || !azureDeploymentName || !azureApiVersion) {
      throw new Error('Azure OpenAI requires Resource Name, Deployment Name, and API Version.');
    }
    return invokeAzureOpenAI(azureResourceName, azureDeploymentName, azureApiVersion, apiKey, message, systemPrompt, maxTokens);
  }

  if (provider === 'gemini' && gcpAccessToken && gcpProjectId) {
    return invokeVertexAI(gcpAccessToken, gcpProjectId, model, message, systemPrompt, temperature, maxTokens);
  }

  const messages = [new SystemMessage(systemPrompt), new HumanMessage(message)];

  let llm: ChatGoogleGenerativeAI | ChatOpenAI | ChatAnthropic;

  if (provider === 'gemini') {
    llm = new ChatGoogleGenerativeAI({ model, apiKey, temperature, maxOutputTokens: maxTokens });
  } else if (provider === 'openai') {
    llm = new ChatOpenAI({ model, apiKey, temperature, maxTokens });
  } else {
    llm = new ChatAnthropic({ model, apiKey, temperature, maxTokens });
  }

  const response = await llm.invoke(messages);
  const content = response.content;
  return typeof content === 'string' ? content : JSON.stringify(content);
}

export function listModels(provider: ProviderName): string[] {
  return PROVIDER_MODELS[provider] ?? [];
}
