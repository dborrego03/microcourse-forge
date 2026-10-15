"use client";

import { useActionState } from "react";

import { narrateLesson, type FormState } from "../../actions";

export function NarrateButton({ lessonId }: { lessonId: number }) {
  const [state, action, pending] = useActionState<FormState>(narrateLesson.bind(null, lessonId), {
    error: null,
  });
  return (
    <form action={action} className="inline">
      <button
        type="submit"
        disabled={pending}
        className="text-sm text-teal-800 underline hover:text-teal-950"
      >
        {pending ? "Recording the narration…" : "Add narration (synthetic voice)"}
      </button>
      <span role="status" aria-live="polite" className="ml-2 text-sm text-red-800">
        {state.error}
      </span>
    </form>
  );
}
