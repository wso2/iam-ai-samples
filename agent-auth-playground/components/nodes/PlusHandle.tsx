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
import { Handle, Position } from 'reactflow';

interface PlusHandleProps {
  type: 'source' | 'target';
  position: Position;
  id?: string;
  connected?: boolean;
  alwaysShow?: boolean;
}

export default function PlusHandle({ type, position, id, connected = false, alwaysShow = false }: PlusHandleProps) {
  const showPlus = !connected || alwaysShow;

  if (!showPlus) {
    return <Handle type={type} position={position} id={id} />;
  }

  return (
    <Handle
      type={type}
      position={position}
      id={id}
      style={{
        width: 15,
        height: 15,
        background: 'white',
        border: '2px solid #000',
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'crosshair',
        boxShadow: '0 1px 4px rgba(0,0,0,0.2)',
      }}
    >
      <span
        style={{
          fontSize: 13,
          fontWeight: 700,
          color: '#000',
          lineHeight: 1,
          pointerEvents: 'none',
          userSelect: 'none',
          marginTop: -1,
        }}
      >
        +
      </span>
    </Handle>
  );
}
