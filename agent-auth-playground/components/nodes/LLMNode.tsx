import { Handle, Position } from 'reactflow';
import GoogleImage from '../assets/google-logo.png';
import OpenaiImage from '../assets/openai-logo.png';
import AnthropicImage from '../assets/anthropic-logo.png';
import AzureOpenAIImage from '../assets/azure-openai-logo.png';
import LLMImage from '../assets/llm.png';
import ActiveBorder from './ActiveBorder';

const PROVIDER_META: Record<string, { label: string; logoSrc?: string }> = {
  gemini: { label: 'Google Gemini', logoSrc: GoogleImage.src },
  openai: { label: 'OpenAI', logoSrc: OpenaiImage.src },
  anthropic: { label: 'Anthropic', logoSrc: AnthropicImage.src },
  'azure-openai': { label: 'Azure OpenAI', logoSrc: AzureOpenAIImage.src },
};

const PLACEHOLDER_META = { label: 'Select a model', logoSrc: LLMImage.src };

export default function LLMNode({ data }: any) {
  const providerMeta = data?.provider ? PROVIDER_META[data.provider] : undefined;
  const { label, logoSrc } = providerMeta ?? PLACEHOLDER_META;
  const isActive = !!data?.isActive;

  return (
    <div className="flex flex-col items-center gap-2 text-slate-900">
      <ActiveBorder active={isActive} rx="50%">
        <div className="relative h-20 w-20 rounded-full bg-white shadow-lg border-2 border-slate-200">
          <div className="flex h-full w-full items-center justify-center">
            {logoSrc ? (
              <img src={logoSrc} alt={label} className="h-12 w-12 object-contain" />
            ) : (
              <span className="text-xs font-semibold text-slate-600 text-center px-1">{label}</span>
            )}
          </div>
          <Handle type="target" position={Position.Bottom} id="bottom" />
        </div>
      </ActiveBorder>
      <div className="text-xs font-medium text-slate-700">{label}</div>
    </div>
  );
}
