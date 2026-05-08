import { NextRequest } from 'next/server';
import { WorkflowExecutor, WorkflowEvent } from '@/lib/workflowExecutor';
import { validateWorkflow } from '@/lib/workflowValidation';

export const maxDuration = 60;

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body) {
    return sseError('Invalid request body');
  }

  const { workflow, input, workflowId, llmCredentials, agentCredentials, memoryMessages, oboTokens, mcpDiscoveredTools } = body;

  if (!workflow || !input) {
    return sseError('Missing workflow or input');
  }

  const validation = validateWorkflow(workflow, {
    mcpDiscoveredTools:
      mcpDiscoveredTools && typeof mcpDiscoveredTools === 'object' ? mcpDiscoveredTools : undefined,
  });
  if (!validation.valid) {
    return sseError(`Invalid workflow: ${validation.errors.join(', ')}`);
  }

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (data: unknown) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      const onEvent = (event: WorkflowEvent) => {
        send(event);
      };

      try {
        console.log('Executing workflow:', workflowId);

        const executor = new WorkflowExecutor(
          workflow,
          input,
          workflowId || 'temp',
          Array.isArray(llmCredentials) ? llmCredentials : [],
          Array.isArray(agentCredentials) ? agentCredentials : [],
          request.nextUrl.origin,
          Array.isArray(memoryMessages) ? memoryMessages : [],
          oboTokens && typeof oboTokens === 'object' ? oboTokens : {},
          onEvent,
          mcpDiscoveredTools && typeof mcpDiscoveredTools === 'object' ? mcpDiscoveredTools : {}
        );
        const result = await executor.execute();

        console.log('Workflow execution result:', {
          success: result.success,
          hasError: !!result.error,
          executionTime: result.executionTime,
        });

        send({
          type: 'result',
          success: result.success,
          output: result.output,
          error: result.error,
          executionTime: result.executionTime,
          trace: result.trace,
          requiresConsent: result.requiresConsent,
        });
      } catch (error) {
        console.error('Workflow API error:', error);
        send({
          type: 'result',
          success: false,
          error: error instanceof Error ? error.message : 'Internal server error',
        });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

function sseError(message: string) {
  const encoder = new TextEncoder();
  const body = `data: ${JSON.stringify({ type: 'result', success: false, error: message })}\n\n`;
  return new Response(encoder.encode(body), {
    status: 400,
    headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
  });
}
