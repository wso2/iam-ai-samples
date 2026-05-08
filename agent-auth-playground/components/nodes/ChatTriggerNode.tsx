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
import { Position } from 'reactflow';
import ChatTriggerImage from '../assets/chat.png';
import ActiveBorder from './ActiveBorder';
import PlusHandle from './PlusHandle';

export default function ChatTriggerNode({ data }: any) {
  const isActive = !!data?.isActive;
  const connected: string[] = data?.connectedSourceHandles ?? [];
  return (
    <div className="flex flex-col items-center gap-2 text-slate-900">
      <ActiveBorder active={isActive} rx={8}>
        <div className="relative flex h-25 w-25 items-center justify-center rounded-lg bg-white shadow-lg border-2 border-slate-200">
          <img
            src={ChatTriggerImage.src}
            alt="Chat Trigger"
            className="h-15 w-15 object-contain"
          />
          <PlusHandle type="source" position={Position.Right} connected={connected.includes('__default__')} />
        </div>
      </ActiveBorder>
      <div className="text-xs font-medium text-slate-700">Chat Trigger</div>
    </div>
  );
}
