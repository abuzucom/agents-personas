export default function SettingsPanel() {
  return (
    <section
      style={{
        background: "#ffffff",
        color: "#1a1a1a",
        border: "1px solid #e5e7eb",
        padding: "24px",
      }}
    >
      <h2 style={{ color: "#374151" }}>Preferences</h2>
      <p style={{ color: "#6b7280" }}>
        Choose how the application behaves for this account.
      </p>
      <button
        style={{
          background: "#f3f4f6",
          color: "#111827",
          border: "1px solid #d1d5db",
        }}
      >
        Edit profile
      </button>
    </section>
  );
}
