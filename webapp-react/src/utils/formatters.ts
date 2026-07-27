export const formatPrice = (price: number | undefined | null): string => {
  if (price === undefined || price === null || price === 0) return "0.00";
  const absPrice = Math.abs(price);
  if (absPrice < 0.01) {
    // For very small numbers like crypto (SHIB, PEPE), show up to 6 decimal places, removing trailing zeros
    return parseFloat(price.toFixed(8)).toString();
  }
  return price.toFixed(2);
};
