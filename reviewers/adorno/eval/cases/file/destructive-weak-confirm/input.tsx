import { useEffect, useRef, useState } from "react";

export default function WorkspaceDanger({ workspaceId }: { workspaceId: string }) {
  const [open, setOpen] = useState(false);
  const okRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) okRef.current?.focus();
  }, [open]);

  async function handleDelete() {
    await fetch(`/api/workspaces/${workspaceId}`, { method: "DELETE" });
    setOpen(false);
  }

  return (
    <section>
      <h2>Workspace settings</h2>
      <button onClick={() => setOpen(true)}>Delete workspace</button>
      {open && (
        <div role="dialog" aria-modal="true">
          <p>Are you sure?</p>
          <button ref={okRef} onClick={handleDelete}>
            OK
          </button>
          <button onClick={() => setOpen(false)}>Cancel</button>
        </div>
      )}
    </section>
  );
}
