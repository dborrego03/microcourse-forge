// Only used on the server (server components and actions), so the API never needs CORS.
export const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

export type Source = {
  id: number;
  section: string;
  pages: string;
  text: string;
  title: string;
  license: string;
  license_url: string;
  attribution: string;
  source_url: string;
};

export type Question = {
  objective: number;
  type: "multiple_choice" | "true_false" | "short_answer";
  question: string;
  options: string[];
  answer: string;
  feedback: string;
  source: number;
};

export type Lesson = {
  id: number;
  status: "running" | "ready" | "failed";
  request: { topic: string; objectives: string[]; level: string };
  lesson: {
    title: string;
    objectives: string[];
    sections: { heading: string; body: string; example: string | null; sources: number[] }[];
    summary: string;
  } | null;
  quiz: { questions: Question[] } | null;
  model: string | null;
  prompt_version: string | null;
  created_at: string;
  sources: Source[];
  audio: { part: number; duration_s: number }[];
};

export type LessonSummary = {
  id: number;
  status: string;
  topic: string;
  title: string | null;
  created_at: string;
};

async function get<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_URL}${path}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GET ${path} failed with ${res.status}`);
  return res.json();
}

export const getLesson = (id: string) => get<Lesson>(`/lessons/${encodeURIComponent(id)}`);
export const listLessons = () => get<LessonSummary[]>("/lessons?limit=10");
