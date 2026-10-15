"use server";

import { redirect } from "next/navigation";

import { API_URL } from "./lib/api";

export type FormState = { error: string | null };

export async function createLesson(_prev: FormState, form: FormData): Promise<FormState> {
  const topic = String(form.get("topic") ?? "").trim();
  const objectives = String(form.get("objectives") ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const level = form.get("level") === "intermediate" ? "intermediate" : "beginner";

  if (topic.length < 3 || topic.length > 200) return { error: "The topic needs 3 to 200 characters." };
  if (objectives.length > 4) return { error: "Use at most 4 objectives, one per line." };

  const res = await fetch(`${API_URL}/lessons`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ topic, objectives, level }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : (body?.detail?.message ?? `the API answered ${res.status}`);
    return { error: `Couldn't create the lesson: ${detail}` };
  }
  const lesson = await res.json();
  redirect(`/lessons/${lesson.id}`);
}

export async function narrateLesson(lessonId: number): Promise<FormState> {
  const res = await fetch(`${API_URL}/lessons/${lessonId}/audio`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    return { error: `Couldn't narrate the lesson: ${body?.detail ?? `the API answered ${res.status}`}` };
  }
  redirect(`/lessons/${lessonId}`);
}
