export default function SessionTimeoutDialog({ onClose }: { onClose: () => void }) {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="timeout-title">
      <h2 id="timeout-title">Your session has expired</h2>
      <p>For security reasons, signed-in access has ended.</p>
      <button onClick={onClose}>Dismiss</button>
    </div>
  );
}
