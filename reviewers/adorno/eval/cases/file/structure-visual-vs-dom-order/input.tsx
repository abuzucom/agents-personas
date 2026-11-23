export default function PricingTiers() {
  return (
    <div className="pricing-grid">
      <a href="/checkout/enterprise" className="card" style={{ order: 1 }}>
        <h2>Enterprise</h2>
        <p>Custom annual agreement.</p>
      </a>
      <a href="/checkout/starter" className="card" style={{ order: 3 }}>
        <h2>Starter</h2>
        <p>For individuals and trials.</p>
      </a>
      <a href="/checkout/team" className="card" style={{ order: 2 }}>
        <h2>Team</h2>
        <p>For growing organizations.</p>
      </a>
    </div>
  );
}
