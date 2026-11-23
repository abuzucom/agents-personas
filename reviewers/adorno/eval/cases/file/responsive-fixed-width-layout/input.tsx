export default function MetricsDashboard() {
  return (
    <main style={{ width: "1280px", margin: "0 auto" }}>
      <h1>Revenue overview</h1>
      <div style={{ display: "flex", width: "1280px", gap: "24px" }}>
        <section style={{ width: "300px", flexShrink: 0 }}>
          <h2>Monthly recurring</h2>
          <p>$48,200</p>
        </section>
        <section style={{ width: "300px", flexShrink: 0 }}>
          <h2>Churn</h2>
          <p>1.8 percent</p>
        </section>
        <section style={{ width: "300px", flexShrink: 0 }}>
          <h2>New accounts</h2>
          <p>216</p>
        </section>
        <aside style={{ width: "344px", flexShrink: 0 }}>
          <h2>Notes</h2>
          <p>Quarterly planning review on Friday.</p>
        </aside>
      </div>
    </main>
  );
}
