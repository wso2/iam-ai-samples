import React from 'react';
import { LoadingSpinnerProps } from '../../types';

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ 
  size = 'md', 
  className = '' 
}) => {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12'
  };

  return (
    <div className={`flex justify-center items-center ${className}`}>
      <div 
        className={`animate-spin rounded-full border-2 border-secondary-300 border-t-primary-600 ${sizeClasses[size]}`}
      />
    </div>
  );
};

export default LoadingSpinner;