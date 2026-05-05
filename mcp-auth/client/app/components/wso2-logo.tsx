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

interface WSO2LogoProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  showText?: boolean;
  className?: string;
}

export function WSO2Logo({ size = 'md', showText = true, className = '' }: WSO2LogoProps) {
  const sizeClasses = {
    sm: 'w-6 h-6',
    md: 'w-8 h-8',
    lg: 'w-10 h-10',
    xl: 'w-12 h-12'
  };

  const textSizeClasses = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-lg',
    xl: 'text-xl'
  };

  return (
    <div className={`flex items-center space-x-2 ${className}`}>
      {/* WSO2 Logo Icon */}
      <div className={`${sizeClasses[size]} bg-gradient-to-br from-wso2-primary-500 to-wso2-primary-600 rounded-lg flex items-center justify-center shadow-wso2-sm`}>
        <svg
          viewBox="0 0 24 24"
          className="w-2/3 h-2/3 text-white"
          fill="currentColor"
        >
          {/* Stylized "W" for WSO2 */}
          <path d="M3 4L7 20L9.5 10L12 20L14.5 10L17 20L21 4H19L16.5 14L14.5 6L12 14L9.5 6L7.5 14L5 4H3Z" />
        </svg>
      </div>

      {/* WSO2 Text */}
      {showText && (
        <div className="flex flex-col">
          <span className={`font-bold text-wso2-gray-900 dark:text-white ${textSizeClasses[size]} leading-none`}>
            WSO2
          </span>
          {size !== 'sm' && (
            <span className="text-xs text-wso2-gray-500 dark:text-wso2-gray-400 leading-none">
              Open Source Platform
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export function WSO2ProductLogo({
  productName,
  size = 'md',
  className = ''
}: {
  productName: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
}) {
  const sizeClasses = {
    sm: 'w-6 h-6',
    md: 'w-8 h-8',
    lg: 'w-10 h-10',
    xl: 'w-12 h-12'
  };

  const textSizeClasses = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-lg',
    xl: 'text-xl'
  };

  return (
    <div className={`flex items-center space-x-3 ${className}`}>
      {/* Product Icon */}
      <div className={`${sizeClasses[size]} bg-gradient-to-br from-wso2-primary-500 to-wso2-primary-600 rounded-lg flex items-center justify-center shadow-wso2-sm`}>
        <svg
          viewBox="0 0 24 24"
          className="w-2/3 h-2/3 text-white"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        >
          {/* AI/Bot Icon for MCP Agent */}
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423L16.5 15.75l.394 1.183a2.25 2.25 0 001.423 1.423L19.5 18.75l-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
        </svg>
      </div>

      {/* Product Name and WSO2 Branding */}
      <div className="flex flex-col">
        <span className={`font-bold text-wso2-gray-900 dark:text-white ${textSizeClasses[size]} leading-tight`}>
          {productName}
        </span>
        <span className="text-xs text-wso2-gray-500 dark:text-wso2-gray-400 leading-none">
          Powered by WSO2
        </span>
      </div>
    </div>
  );
}