import { API_URL } from "../../../lib/api";

// Passes the package through so the browser never talks to the API directly.
export async function GET(_request: Request, { params }: RouteContext<"/lessons/[id]/scorm">) {
  const { id } = await params;
  const res = await fetch(`${API_URL}/lessons/${encodeURIComponent(id)}/scorm`);
  if (!res.ok) return new Response("Package not available", { status: res.status });
  return new Response(res.body, {
    headers: {
      "content-type": "application/zip",
      "content-disposition": res.headers.get("content-disposition") ?? "attachment",
    },
  });
}
