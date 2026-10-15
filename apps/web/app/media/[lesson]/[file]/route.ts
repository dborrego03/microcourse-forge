import { API_URL } from "../../../lib/api";

export async function GET(_request: Request, { params }: RouteContext<"/media/[lesson]/[file]">) {
  const { lesson, file } = await params;
  // Only the shapes the API serves, so this can't be used to reach other API paths.
  if (!/^lesson-\d+$/.test(lesson) || !/^part-\d+\.(mp3|vtt)$/.test(file)) {
    return new Response("Not found", { status: 404 });
  }
  const res = await fetch(`${API_URL}/media/${lesson}/${file}`);
  if (!res.ok) return new Response("Not found", { status: res.status });
  return new Response(res.body, {
    headers: { "content-type": res.headers.get("content-type") ?? "application/octet-stream" },
  });
}
