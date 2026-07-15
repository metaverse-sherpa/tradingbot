/**
 * Checks if the US stock market is currently open.
 * US Stock Market regular hours are Monday through Friday, 9:30 AM to 4:00 PM Eastern Time.
 */
export const isStockMarketOpen = (): boolean => {
  const now = new Date();
  
  // Format the current time in America/New_York
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: 'numeric',
    minute: 'numeric',
    weekday: 'short',
    hour12: false
  });
  
  const parts = formatter.formatToParts(now);
  const weekday = parts.find(p => p.type === 'weekday')?.value;
  const hour = parseInt(parts.find(p => p.type === 'hour')?.value || '0', 10);
  const minute = parseInt(parts.find(p => p.type === 'minute')?.value || '0', 10);

  // Market is closed on weekends
  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }

  const timeInMinutes = hour * 60 + minute;
  const startMinutes = 9 * 60 + 30; // 9:30 AM
  const endMinutes = 16 * 60;      // 4:00 PM

  return timeInMinutes >= startMinutes && timeInMinutes < endMinutes;
};
