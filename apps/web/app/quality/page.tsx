import { Suspense } from "react";

import { getMetrics, type Metrics } from "../lib/api";

export const metadata = { title: "Quality · microcourse-forge" };

const th = "border-b border-stone-300 px-3 py-2 text-left font-medium";
const td = "border-b border-stone-200 px-3 py-2 tabular-nums";

export default function QualityPage() {
  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-semibold">Quality</h1>
        <p className="mt-2 text-stone-700">
          Latest evaluation runs and how the pipeline behaves on the requests it has served. Every number here
          comes from the database and can be reproduced with the commands in the README.
        </p>
      </header>
      <Suspense fallback={<p className="text-stone-600">Loading…</p>}>
        <Panels />
      </Suspense>
    </div>
  );
}

async function Panels() {
  const data = await getMetrics().catch(() => null);
  if (!data) return <p className="text-red-800">The API isn&apos;t reachable.</p>;
  return (
    <>
      <Evals evals={data.evals} />
      <Steps steps={data.steps} />
      <section aria-labelledby="blocked">
        <h2 id="blocked" className="mb-3 text-xl font-semibold">
          Requests blocked by the guardrails
        </h2>
        {data.blocked.length === 0 ? (
          <p className="text-stone-600">None yet.</p>
        ) : (
          <ul className="list-disc pl-6">
            {data.blocked.map((b) => (
              <li key={b.rule}>
                {b.rule.replace("_", " ")}: {b.requests}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-sm text-stone-600">
          Lessons: {data.lessons.map((l) => `${l.lessons} ${l.status}`).join(", ") || "none"}.
        </p>
      </section>
    </>
  );
}

function Evals({ evals }: { evals: Metrics["evals"] }) {
  return (
    <section aria-labelledby="evals">
      <h2 id="evals" className="mb-3 text-xl font-semibold">
        Evaluations
      </h2>
      <div className="space-y-8">
        {Object.entries(Object.groupBy(evals, (e) => e.kind)).map(([kind, runs = []]) => {
          // One column per mode (retrieval) or dataset (guardrails), so they can be compared.
          const label = (e: Metrics["evals"][number]) =>
            typeof e.config.mode === "string" ? e.config.mode : e.dataset;
          const names = [...new Set(runs.flatMap((e) => Object.keys(e.metrics)))];
          return (
            <div key={kind} className="overflow-x-auto">
              <h3 className="font-medium capitalize">{kind}</h3>
              <table className="mt-2 w-full border-collapse bg-white text-sm">
                <thead>
                  <tr>
                    <th className={th}>Metric</th>
                    {runs.map((e) => (
                      <th key={label(e)} className={th}>
                        {label(e)}
                        <span className="block font-normal text-stone-600">
                          {e.git_sha}, {new Date(e.created_at).toISOString().slice(0, 10)}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {names.map((name) => (
                    <tr key={name}>
                      <th scope="row" className={th}>
                        {name}
                      </th>
                      {runs.map((e) => (
                        <td key={label(e)} className={td}>
                          {e.metrics[name] ?? "–"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Steps({ steps }: { steps: Metrics["steps"] }) {
  const seconds = (ms: number | null) => (ms === null ? "–" : `${(ms / 1000).toFixed(1)} s`);
  return (
    <section aria-labelledby="steps" className="overflow-x-auto">
      <h2 id="steps" className="mb-3 text-xl font-semibold">
        Pipeline steps
      </h2>
      <table className="w-full border-collapse bg-white text-sm">
        <thead>
          <tr>
            <th className={th}>Step</th>
            <th className={th}>Runs</th>
            <th className={th}>Cache hits</th>
            <th className={th}>p50</th>
            <th className={th}>p95</th>
            <th className={th}>Avg. cost</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((s) => (
            <tr key={s.step}>
              <th scope="row" className={th}>
                {s.step}
              </th>
              <td className={td}>{s.runs}</td>
              <td className={td}>{Math.round(s.cache_hit_rate * 100)}%</td>
              <td className={td}>{seconds(s.p50_ms)}</td>
              <td className={td}>{seconds(s.p95_ms)}</td>
              <td className={td}>{s.avg_cost_usd === null ? "–" : `$${s.avg_cost_usd.toFixed(4)}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-sm text-stone-600">
        Latency and cost only count calls that reached the model; cache hits take a few milliseconds. Cost is
        the estimate at API list prices.
      </p>
    </section>
  );
}
