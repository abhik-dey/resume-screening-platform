import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { askRag, searchResumes } from "../api/endpoints";
import type { RagAnswer, SearchResponse } from "../api/types";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, inputClass, Spinner } from "../components/ui";

type Mode = "search" | "ask";

export function SearchPage() {
  const [mode, setMode] = useState<Mode>("search");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [answer, setAnswer] = useState<RagAnswer | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResults(null);
    setAnswer(null);
    try {
      if (mode === "search") setResults(await searchResumes(query));
      else setAnswer(await askRag(query));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The request failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-semibold text-ink">Find candidates</h1>
        <p className="text-sm text-ink-soft mt-0.5">
          Search returns matching resumes. Asking a question reads across several and answers it.
        </p>
      </div>

      <Card className="p-5">
        <div className="flex gap-1 mb-4 p-1 bg-surface-sunk rounded w-fit">
          {(["search", "ask"] as Mode[]).map((option) => (
            <button key={option} onClick={() => setMode(option)}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                mode === option ? "bg-surface text-ink shadow-sm font-medium" : "text-ink-soft"
              }`}>
              {option === "search" ? "Search resumes" : "Ask a question"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="flex gap-2">
          <input className={inputClass} value={query} required
            onChange={(e) => setQuery(e.target.value)}
            placeholder={mode === "search"
              ? "distributed systems, payment infrastructure"
              : "Which candidates have production Kubernetes experience?"} />
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? <Spinner /> : mode === "search" ? "Search" : "Ask"}
          </Button>
        </form>

        <p className="text-xs text-ink-faint mt-2.5 leading-relaxed">
          {mode === "search"
            ? "Matches on meaning, so wording doesn't have to line up exactly. Candidates must be screened first to appear."
            : "Answers are built only from indexed resumes, and every claim cites the resume it came from."}
        </p>
      </Card>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {results && <SearchResults results={results} />}
      {answer && <RagResult answer={answer} />}
    </div>
  );
}

function SearchResults({ results }: { results: SearchResponse }) {
  if (results.total_hits === 0) {
    return (
      <Card>
        <EmptyState
          title="No matches"
          hint="Candidates appear here once they've been screened. Run screening on a job first."
        />
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader title={`${results.total_hits} matches`} />
      <ul className="divide-y divide-line">
        {results.results.map((hit) => (
          <li key={hit.resume_id}>
            <Link to={`/resumes/${hit.resume_id}`}
              className="flex items-center justify-between gap-4 px-5 py-3 hover:bg-surface-sunk">
              <div className="min-w-0">
                <p className="text-sm text-ink">{hit.candidate_name ?? "Unidentified candidate"}</p>
                <p className="text-xs text-ink-faint truncate">{hit.original_filename}</p>
              </div>
              <span className="numeric text-sm text-ink-soft">{hit.similarity.toFixed(2)}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="px-5 py-2.5 text-xs text-ink-faint border-t border-line">
        Ranked by similarity using {results.embedding_model}.
      </p>
    </Card>
  );
}

/* Renders the answer alongside the sources it came from.
 *
 * The backend strips claims that cite sources which don't exist, and
 * withholds the whole answer if none survive. Both states are surfaced
 * here rather than smoothed over — an answer that was rejected for being
 * ungrounded must not read like an answer. */
function RagResult({ answer }: { answer: RagAnswer }) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title={answer.answer_rejected ? "Answer withheld" : "Answer"} />
        <div className="px-5 py-4 space-y-4">
          {answer.answer_rejected && (
            <div className="border-l-2 border-negative pl-3">
              <p className="text-xs text-negative leading-relaxed">
                None of the claims in the generated answer could be traced to the retrieved
                resumes, so it wasn't shown. The sources are below if you want to read them
                directly.
              </p>
            </div>
          )}

          <p className="text-sm text-ink leading-relaxed">{answer.answer}</p>

          {answer.insufficient_evidence && !answer.answer_rejected && (
            <p className="text-xs text-caution leading-relaxed">
              The indexed resumes don't contain enough information to answer this fully.
            </p>
          )}

          {answer.claims.length > 0 && (
            <div>
              <p className="eyebrow mb-2">Claims and their sources</p>
              <ul className="space-y-2">
                {answer.claims.map((claim, index) => (
                  <li key={index} className="text-sm text-ink-soft leading-relaxed flex gap-2">
                    <span className="numeric text-xs text-signal shrink-0 mt-0.5">
                      [{claim.source_ids.join(", ")}]
                    </span>
                    <span>{claim.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {answer.citation_warnings.length > 0 && (
            <div className="border-l-2 border-signal pl-3">
              <p className="eyebrow mb-1">Removed from the answer</p>
              <ul className="space-y-1">
                {answer.citation_warnings.map((warning, index) => (
                  <li key={index} className="text-xs text-caution leading-relaxed">{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Card>

      {answer.sources.length > 0 && (
        <Card>
          <CardHeader title={`Sources · ${answer.sources.length}`} />
          <ul className="divide-y divide-line">
            {answer.sources.map((source) => (
              <li key={source.source_id} className="px-5 py-3">
                <div className="flex items-center justify-between gap-3 mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="numeric text-xs text-signal">[{source.source_id}]</span>
                    <Link to={`/resumes/${source.resume_id}`}
                      className="text-sm text-ink hover:text-accent">
                      {source.candidate_name}
                    </Link>
                  </div>
                  <span className="numeric text-xs text-ink-faint">
                    {source.similarity.toFixed(2)}
                  </span>
                </div>
                {/* The full retrieved text, so any claim above can be checked
                    against what the model actually saw. */}
                <p className="text-xs text-ink-soft leading-relaxed whitespace-pre-line bg-surface-sunk rounded p-2.5">
                  {source.text}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
