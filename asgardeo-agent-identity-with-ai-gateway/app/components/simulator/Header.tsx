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

import LayersIcon from '../../../assets/icons/layers.svg';
import SettingsIcon from '../../../assets/icons/settings.svg';

interface HeaderProps {
  onOpenConfig: () => void;
}

export default function Header({ onOpenConfig }: HeaderProps) {
  return (
    <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
      <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-orange-600 rounded-lg flex items-center justify-center">
            <LayersIcon stroke="white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Agent Simulator</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Test AI Gateway with different agent scenarios
            </p>
          </div>
        </div>
        <button
          onClick={onOpenConfig}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
        >
          <SettingsIcon width={20} height={20} />
          Configuration
        </button>
      </div>
    </header>
  );
}
