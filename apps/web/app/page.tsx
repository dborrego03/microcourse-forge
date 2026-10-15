import Link from "next/link";
import { Suspense } from "react";

import { listLessons } from "./lib/api";
import { NewLessonForm } from "./new-lesson-form";

export default function Home() {
  return (
    <div className="space-y-10">
      <section>
        <h1 className="mb-2 text-2xl font-semibold">New micro-course</h1>
        <p className="mb-6 text-stone-700">
          Pick a topic from the Learning, Thinking and Intelligence, or Memory chapters of{" "}
          <em>Psychology 2e</em>. You get a short lesson that cites its sources and a quiz to check it.
        </p>
        <NewLessonForm />
      </section>
      <section>
        <h2 className="mb-3 text-xl font-semibold">Recent lessons</h2>
        <Suspense fallback={<p className="text-stone-600">Loading…</p>}>
          <RecentLessons />
        </Suspense>
      </section>
    </div>
  );
}

async function RecentLessons() {
  const lessons = await listLessons().catch(() => null);
  if (lessons === null) return <p className="text-red-800">The API isn&apos;t reachable.</p>;
  if (lessons.length === 0) return <p className="text-stone-600">None yet.</p>;
  return (
    <ul className="space-y-2">
      {lessons.map((l) => (
        <li key={l.id}>
          <Link href={`/lessons/${l.id}`} className="text-teal-800 underline hover:text-teal-950">
            {l.title ?? l.topic}
          </Link>{" "}
          {l.status !== "ready" && <span className="text-sm text-stone-600">({l.status})</span>}
        </li>
      ))}
    </ul>
  );
}
