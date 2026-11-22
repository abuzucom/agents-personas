export default function InvoicePanel() {
  return (
    <section>
      <h2 style={{ fontSize: "22px" }}>Invoice summary</h2>
      <p style={{ fontSize: "17px" }}>
        The current billing cycle closes on the last day of the month.
      </p>
      <p style={{ fontSize: "13px" }}>
        Past due amounts accrue a late charge after ten days.
      </p>
      <span style={{ fontSize: "11px" }}>
        Tax rates vary by jurisdiction.
      </span>
      <a href="/invoices" style={{ fontSize: "13px" }}>
        View all invoices
      </a>
    </section>
  );
}
