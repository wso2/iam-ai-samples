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

import WarningIcon from '../../../assets/icons/warning.svg';

interface ConfigWarningProps {
  onOpenConfig: () => void;
}

export default function ConfigWarning({ onOpenConfig }: ConfigWarningProps) {
  return (
    <div className="mb-6 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg flex items-center gap-3">
      <WarningIcon className="text-yellow-600 dark:text-yellow-400" />
      <span className="text-sm text-yellow-700 dark:text-yellow-300">
        Please configure all settings before running simulations.
      </span>
      <button
        onClick={onOpenConfig}
        className="ml-auto px-3 py-1 text-sm font-medium text-yellow-700 dark:text-yellow-300 bg-yellow-100 dark:bg-yellow-900/40 hover:bg-yellow-200 dark:hover:bg-yellow-900/60 rounded-lg transition-colors"
      >
        Open Configuration
      </button>
    </div>
  );
}
