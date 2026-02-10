/**
 Copyright (c) 2026, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.
 
 This software is the property of WSO2 LLC. and its suppliers, if any.
 Dissemination of any information or reproduction of any material contained
 herein is strictly forbidden, unless permitted by WSO2 in accordance with
 the WSO2 Commercial License available at http://wso2.com/licenses.
 For specific language governing the permissions and limitations under
 this license, please see the license as well as any agreement you’ve
 entered into with WSO2 governing the purchase of this software and any
 */

'use client';

interface ConfigWarningProps {
  onOpenConfig: () => void;
}

export default function ConfigWarning({ onOpenConfig }: ConfigWarningProps) {
  return (
    <div className="mb-6 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg flex items-center gap-3">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-yellow-600 dark:text-yellow-400">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
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
