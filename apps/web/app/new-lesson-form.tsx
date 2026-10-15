"use client";

import { useActionState } from "react";

import { createLesson, type FormState } from "./actions";

const input =
  "w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-stone-900 " +
  "focus:outline-none focus:ring-2 focus:ring-teal-700";

export function NewLessonForm() {
  const [state, action, pending] = useActionState<FormState, FormData>(createLesson, { error: null });

  return (
    <form action={action} className="space-y-4">
      <div>
        <label htmlFor="topic" className="mb-1 block font-medium">
          Topic
        </label>
        <input
          id="topic"
          name="topic"
          required
          minLength={3}
          maxLength={200}
          className={input}
          placeholder="e.g. Classical conditioning"
        />
      </div>
      <div>
        <label htmlFor="objectives" className="mb-1 block font-medium">
          Learning objectives <span className="font-normal text-stone-600">(optional, one per line)</span>
        </label>
        <textarea
          id="objectives"
          name="objectives"
          rows={3}
          className={input}
          placeholder="Explain how a neutral stimulus becomes a conditioned stimulus"
        />
      </div>
      <div>
        <label htmlFor="level" className="mb-1 block font-medium">
          Level
        </label>
        <select id="level" name="level" className={input}>
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
        </select>
      </div>
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-teal-800 px-4 py-2 font-medium text-white hover:bg-teal-900 focus:outline-none focus:ring-2 focus:ring-teal-700 focus:ring-offset-2 disabled:opacity-60"
      >
        {pending ? "Writing the lesson… (about 30 s)" : "Create micro-course"}
      </button>
      <p role="status" aria-live="polite" className="text-red-800">
        {state.error}
      </p>
    </form>
  );
}
