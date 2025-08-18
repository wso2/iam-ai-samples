import React from 'react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { ErrorMessageProps } from '../../types';

const ErrorMessage: React.FC<ErrorMessageProps> = ({ message, className = '' }) => {
  return (
    <div className={`flex items-center gap-2 text-red-600 bg-red-50 p-4 rounded-lg border border-red-200 ${className}`}>
      <ExclamationTriangleIcon className="w-5 h-5 flex-shrink-0" />
      <p className="text-sm">{message}</p>
    </div>
  );
};

export default ErrorMessage;