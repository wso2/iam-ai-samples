import { NextRequest, NextResponse } from 'next/server';
import { invokeLLM, ProviderName, PROVIDER_MODELS } from '@/lib/llmProviders';

export const maxDuration = 60;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const {
      provider, model, message, systemPrompt, temperature, maxTokens,
      apiKey, gcpAccessToken, gcpProjectId,
      azureResourceName, azureDeploymentName, azureApiVersion,
    } = body;

    const isAzure = provider === 'azure-openai';
    const isGcpAuth = provider === 'gemini' && gcpAccessToken && gcpProjectId;

    if (!provider || !message) {
      return NextResponse.json(
        { success: false, error: 'Missing required parameters' },
        { status: 400 }
      );
    }

    if (!isAzure && !model) {
      return NextResponse.json(
        { success: false, error: 'Missing required parameter: model' },
        { status: 400 }
      );
    }

    if (isAzure && (!azureResourceName || !azureDeploymentName || !azureApiVersion)) {
      return NextResponse.json(
        { success: false, error: 'Azure OpenAI requires azureResourceName, azureDeploymentName, and azureApiVersion.' },
        { status: 400 }
      );
    }

    if (!(provider in PROVIDER_MODELS)) {
      return NextResponse.json(
        { success: false, error: `Unknown provider: ${provider}` },
        { status: 400 }
      );
    }

    if (!isGcpAuth && !apiKey) {
      return NextResponse.json(
        { success: false, error: `No API key found for ${provider}. Please configure your API key in Settings.` },
        { status: 401 }
      );
    }

    const output = await invokeLLM(
      provider as ProviderName,
      apiKey ?? '',
      model ?? '',
      message,
      systemPrompt ?? '',
      temperature ?? 0.7,
      maxTokens ?? 1000,
      gcpAccessToken,
      gcpProjectId,
      azureResourceName,
      azureDeploymentName,
      azureApiVersion
    );

    return NextResponse.json({ success: true, output });
  } catch (error) {
    console.error('LLM API error:', error);
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : 'Internal server error' },
      { status: 500 }
    );
  }
}
