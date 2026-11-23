export function SaveButton({ label }: { label: string }) {
  return (
    <div
      className="save-btn"
      onClick={() => {
        console.log("save requested", label);
      }}
    >
      {label}
    </div>
  );
}
