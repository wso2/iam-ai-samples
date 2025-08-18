// Helper function to get current date in Sri Lanka timezone (UTC+5:30)
export const getSriLankaDate = (): Date => {
  const now = new Date();
  // Sri Lanka is UTC+5:30
  const sriLankaOffset = 5.5 * 60 * 60 * 1000; // 5.5 hours in milliseconds
  const utc = now.getTime() + (now.getTimezoneOffset() * 60 * 1000);
  return new Date(utc + sriLankaOffset);
};

// Format date to yyyy-MM-dd format for input fields
export const formatDateForInput = (date: Date): string => {
  return date.toISOString().split('T')[0];
};
