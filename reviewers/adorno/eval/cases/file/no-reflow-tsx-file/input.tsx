export default function PipelineBoard() {
  return (
    <main style={{ width: "1200px" }}>
      <h1>Deal pipeline</h1>
      <div style={{ display: "flex", width: "1200px" }}>
        <section style={{ width: "400px", flexShrink: 0, whiteSpace: "nowrap" }}>
          <h2>Qualified leads</h2>
          <p>Alder Creek Foods - discovery call booked</p>
        </section>
        <section style={{ width: "400px", flexShrink: 0, whiteSpace: "nowrap" }}>
          <h2>Proposal sent</h2>
          <p>Harborline Logistics - quote under review</p>
        </section>
        <section style={{ width: "400px", flexShrink: 0, whiteSpace: "nowrap" }}>
          <h2>Closed won</h2>
          <p>Juniper Peak Outfitting - contract signed</p>
        </section>
      </div>
    </main>
  );
}
