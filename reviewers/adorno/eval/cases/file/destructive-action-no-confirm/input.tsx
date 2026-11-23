import { useRouter } from "next/router";

export default function ProjectSettings({ projectId }: { projectId: string }) {
  const router = useRouter();

  async function handleDelete() {
    await fetch(`/api/projects/${projectId}`, { method: "DELETE" });
    router.push("/dashboard");
  }

  return (
    <section>
      <h2>Danger zone</h2>
      <p>Deleting this project removes all tasks, comments, and files.</p>
      <button onClick={handleDelete}>Delete project</button>
    </section>
  );
}
