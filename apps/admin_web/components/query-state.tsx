import { Button } from "./ui";
export function QueryState({ title, description, retry, loading = false }: { title: string; description?: string; retry?: () => void; loading?: boolean }) {
  return <div className="query-state" role={retry ? "alert" : "status"} aria-live="polite" aria-busy={loading}>
    {loading && <span className="spinner" aria-hidden="true" />}
    <h2>{title}</h2>{description && <p>{description}</p>}{retry && <Button onClick={retry}>다시 시도</Button>}
  </div>;
}
