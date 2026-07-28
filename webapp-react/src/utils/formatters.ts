export const formatPrice = (price: number | string | undefined | null): string => {
  if (price === undefined || price === null) return "0.00";
  const num = typeof price === 'string' ? parseFloat(price) : price;
  if (isNaN(num) || num === 0) return "0.00";
  const absPrice = Math.abs(num);
  if (absPrice < 0.01) {
    return parseFloat(num.toFixed(11)).toString();
  }
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};
