export function formatShipDate(timestamp: number): string {
  const d = new Date(timestamp);
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const year = d.getFullYear();
  return month + "/" + day + "/" + year;
}

export function formatRenewalDate(timestamp: number): string {
  const d = new Date(timestamp);
  const day = d.getDate();
  const month = d.getMonth() + 1;
  const year = d.getFullYear();
  return day + "/" + month + "/" + year;
}
