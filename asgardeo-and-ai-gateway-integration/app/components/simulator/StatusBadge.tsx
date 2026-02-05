'use client';

interface StatusBadgeProps {
  statusCode: number;
}

export default function StatusBadge({ statusCode }: StatusBadgeProps) {
  if (statusCode >= 200 && statusCode < 300) {
    return (
      <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
        {statusCode} Success
      </span>
    );
  } else if (statusCode >= 400 && statusCode < 500) {
    return (
      <span className="px-2 py-1 text-xs font-medium rounded-full bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
        {statusCode} Client Error
      </span>
    );
  } else {
    return (
      <span className="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
        {statusCode} Error
      </span>
    );
  }
}
