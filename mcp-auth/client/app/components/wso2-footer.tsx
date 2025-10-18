/**
 * Copyright (c) 2025, WSO2 LLC. (https://www.wso2.com).
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

import { WSO2Logo } from './wso2-logo';

export function WSO2Footer() {
  return (
    <div className="border-t border-wso2-gray-200 dark:border-wso2-dark-border p-4 bg-wso2-gray-50 dark:bg-wso2-dark-surface">
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center space-x-4">
          <WSO2Logo size="sm" showText={false} />
          <div className="text-wso2-gray-600 dark:text-wso2-gray-400">
            <span className="font-medium">WSO2 MCP AI Agent</span>
            <span className="mx-2">•</span>
            <span>Empowering digital transformation</span>
          </div>
        </div>

        <div className="flex items-center space-x-4 text-wso2-gray-500 dark:text-wso2-gray-400">
          <a
            href="https://wso2.com"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-wso2-primary-500 transition-colors"
          >
            WSO2.com
          </a>
          <span>•</span>
          <a
            href="https://github.com/wso2"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-wso2-primary-500 transition-colors"
          >
            GitHub
          </a>
          <span>•</span>
          <a
            href="https://wso2.com/contact/"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-wso2-primary-500 transition-colors"
          >
            Support
          </a>
        </div>
      </div>
    </div>
  );
}