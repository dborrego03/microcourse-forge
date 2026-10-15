"use client";

import { useState } from "react";

import type { Question } from "../../lib/api";

export function Quiz({
  questions,
  sourceNumbers,
}: {
  questions: Question[];
  sourceNumbers: Record<number, number>;
}) {
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [checked, setChecked] = useState(false);
  const score = questions.filter((q, i) => q.type !== "short_answer" && answers[i] === q.answer).length;
  const graded = questions.filter((q) => q.type !== "short_answer").length;

  return (
    <section aria-labelledby="quiz" className="rounded-lg border border-stone-200 bg-white p-5">
      <h2 id="quiz" className="mb-4 text-xl font-semibold">
        Check yourself
      </h2>
      <ol className="space-y-6">
        {questions.map((q, i) => (
          <li key={q.question}>
            <fieldset>
              <legend className="mb-2 font-medium">
                {i + 1}. {q.question}
              </legend>
              {q.type === "short_answer" ? (
                <textarea
                  aria-label={`Answer to question ${i + 1}`}
                  rows={2}
                  className="w-full rounded-md border border-stone-300 px-3 py-2"
                  onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })}
                />
              ) : (
                q.options.map((option) => (
                  <label key={option} className="flex items-start gap-2 py-1">
                    <input
                      type="radio"
                      name={`q${i}`}
                      value={option}
                      disabled={checked}
                      className="mt-1"
                      onChange={() => setAnswers({ ...answers, [i]: option })}
                    />
                    <span>{option}</span>
                  </label>
                ))
              )}
            </fieldset>
            {checked && (
              <p className={`mt-2 text-sm ${feedbackColor(q, answers[i])}`}>
                {q.type === "short_answer"
                  ? "Model answer: "
                  : answers[i] === q.answer
                    ? "Correct. "
                    : `Answer: ${q.answer}. `}
                {q.type === "short_answer" && `${q.answer} `}
                {q.feedback}{" "}
                <a href={`#source-${q.source}`} className="underline">
                  [{sourceNumbers[q.source]}]
                </a>
              </p>
            )}
          </li>
        ))}
      </ol>
      <div className="mt-6 flex items-center gap-4">
        <button
          type="button"
          onClick={() => setChecked(!checked)}
          className="rounded-md bg-teal-800 px-4 py-2 font-medium text-white hover:bg-teal-900 focus:outline-none focus:ring-2 focus:ring-teal-700 focus:ring-offset-2"
        >
          {checked ? "Try again" : "Check answers"}
        </button>
        {checked && (
          <p role="status">
            {score} of {graded} correct{graded < questions.length && " (short answers aren't graded)"}
          </p>
        )}
      </div>
    </section>
  );
}

function feedbackColor(q: Question, given: string | undefined) {
  if (q.type === "short_answer") return "text-stone-700";
  return given === q.answer ? "text-green-800" : "text-red-800";
}
