import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  generateFeedback, getFeedback, getQuestions, getResume, getSkills, matchResume,
} from "../api/endpoints";
import type {
  Feedback, InterviewQuestion, MatchResult, Resume, ResumeSkill, ScoreComponent,
} from "../api/types";
import { useCanEdit } from "../auth/AuthContext";
import { AdvisoryNotice, RecommendationBadge, SkillChip, StatusPill } from "../components/Recommendation";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, Spinner } from "../components/ui";

export function CandidatePage() {
  const { resumeId = "" } = useParams();
  const canEdit = useCanEdit();

  const [resume, setResume] = useState<Resume | null>(null);
  const [skills, setSkills] = useState<ResumeSkill[]>([]);
  const [match, setMatch] = useState<MatchResult | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [advisory, setAdvisory] = useState<string>("");
  const [questions, setQuestions] = useState<InterviewQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    getResume(resumeId).then(setResume).catch((c) => setError(c.message));
    getSkills(resumeId).then(setSkills).catch(() => setSkills([]));
    getQuestions(resumeId).then(setQuestions).catch(() => setQuestions([]));
    // Feedback 404s until it's generated — an expected state, not an error.
    getFeedback(resumeId)
      .then((result) => { setFeedback(result.feedback); setAdvisory(result.advisory_notice); })
      .catch(() => setFeedback(null))
      .finally(() => setLoading(false));
  };

  useEffect(load, [resumeId]);

  // Re-running the match returns the component breakdown, which the stored
  // score alone doesn't include — that's what makes the score explainable.
  const rescore = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await matchResume(resumeId);
      setMatch(result);
      if (!result.success) setError(result.reasoning);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Scoring failed");
    } finally {
      setBusy(false);
    }
  };

  const runFeedback = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await generateFeedback(resumeId);
      if (result.success && result.feedback) {
        setFeedback(result.feedback);
        setAdvisory(result.advisory_notice);
      } else {
        setError(result.reasoning);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn't generate feedback");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Card className="p-8 flex justify-center"><Spinner label="Loading candidate" /></Card>;
  if (!resume) return <ErrorBanner message="This candidate couldn't be loaded." />;

  const parsed = (resume.parsed_data ?? {}) as Record<string, any>;
  const components = match?.breakdown?.components as ScoreComponent[] | undefined;

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/jobs/${resume.job_id}`} className="text-sm text-ink-soft hover:text-ink">
          ← Back to job
        </Link>
        <div className="flex items-start justify-between gap-4 mt-2">
          <div>
            <h1 className="text-xl font-semibold text-ink">
              {parsed.full_name ?? resume.original_filename}
            </h1>
            {parsed.email && <p className="text-sm text-ink-soft mt-0.5">{parsed.email}</p>}
          </div>
          <StatusPill status={resume.status} />
        </div>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader
              title="Score"
              action={canEdit && (
                <Button onClick={rescore} disabled={busy}>
                  {busy ? <Spinner /> : components ? "Recompute" : "Compute score"}
                </Button>
              )}
            />
            <div className="px-5 py-4">
              {components ? (
                <>
                  <ScoreBreakdown components={components} score={match!.breakdown.overall_score ?? 0} />
                  {match?.qualitative_analysis_failed && (
                    <p className="mt-4 text-xs text-caution leading-relaxed">
                      The written analysis couldn't be generated. The score above is unaffected —
                      it's computed arithmetically, not by a model.
                    </p>
                  )}
                </>
              ) : (
                <EmptyState
                  title="Not scored yet"
                  hint="Computing a score breaks it into skills, experience, and education contributions against this job's requirements."
                />
              )}
            </div>
          </Card>

          {feedback ? (
            <Card>
              <CardHeader title="Assessment"
                action={<RecommendationBadge value={feedback.recommendation} />} />
              <div className="px-5 py-4 space-y-4">
                <div className="border-l-2 border-signal pl-3">
                  <p className="eyebrow mb-1">How this was determined</p>
                  <p className="text-sm text-ink-soft leading-relaxed">{feedback.threshold_rationale}</p>
                </div>

                {feedback.summary && <p className="text-sm text-ink leading-relaxed">{feedback.summary}</p>}

                {feedback.narrative_generation_failed && (
                  <p className="text-xs text-caution leading-relaxed">
                    The written summary couldn't be generated. The recommendation above still stands —
                    it's derived from the score, not written by a model.
                  </p>
                )}

                <BulletSection title="Strengths" items={feedback.strengths} />
                <BulletSection title="Areas of concern" items={feedback.weaknesses} />
                <BulletSection title="Risk factors" items={feedback.risk_factors}
                  emptyHint="No evidence-based concerns were identified." />
                <BulletSection title="Suggestions for the candidate" items={feedback.improvement_suggestions} />
              </div>
            </Card>
          ) : (
            <Card>
              <CardHeader title="Assessment"
                action={canEdit && (
                  <Button onClick={runFeedback} disabled={busy}>
                    {busy ? <Spinner /> : "Generate"}
                  </Button>
                )}
              />
              <EmptyState
                title="No assessment yet"
                hint="An assessment derives a recommendation from the match score and explains the reasoning. Score the candidate first."
              />
            </Card>
          )}

          {questions.length > 0 && (
            <Card>
              <CardHeader title={`Interview questions · ${questions.length}`} />
              <ul className="divide-y divide-line">
                {questions.map((question) => (
                  <li key={question.id} className="px-5 py-3">
                    <p className="text-sm text-ink leading-relaxed">{question.question}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="eyebrow">{question.category}</span>
                      <span className="text-ink-faint">·</span>
                      <span className="eyebrow">{question.difficulty}</span>
                    </div>
                    {question.rationale && (
                      <p className="text-xs text-ink-faint mt-1.5 leading-relaxed">
                        {question.rationale}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          {advisory && <AdvisoryNotice notice={advisory} />}

          <Card>
            <CardHeader title={`Skills · ${skills.length}`} />
            <div className="px-5 py-4">
              {skills.length === 0 ? (
                <p className="text-xs text-ink-faint">No skills extracted yet.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {skills.map((skill) => <SkillChip key={skill.skill_id} name={skill.name} />)}
                </div>
              )}
            </div>
          </Card>

          {match?.score && match.score.missing_skills.length > 0 && (
            <Card>
              <CardHeader title="Missing requirements" />
              <div className="px-5 py-4 flex flex-wrap gap-1.5">
                {match.score.missing_skills.map((skill) => (
                  <SkillChip key={skill} name={skill} missing />
                ))}
              </div>
            </Card>
          )}

          {Array.isArray(parsed.experience) && parsed.experience.length > 0 && (
            <Card>
              <CardHeader title="Experience" />
              <ul className="px-5 py-4 space-y-3">
                {parsed.experience.map((role: any, index: number) => (
                  <li key={index}>
                    <p className="text-sm text-ink">{role.title}</p>
                    <p className="text-xs text-ink-soft">
                      {role.company}
                      {role.start_date && ` · ${role.start_date}–${role.end_date ?? "present"}`}
                    </p>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function BulletSection({ title, items, emptyHint }: {
  title: string; items: string[]; emptyHint?: string;
}) {
  if (items.length === 0 && !emptyHint) return null;
  return (
    <div>
      <p className="eyebrow mb-1.5">{title}</p>
      {items.length === 0 ? (
        <p className="text-xs text-ink-faint">{emptyHint}</p>
      ) : (
        <ul className="space-y-1">
          {items.map((item, index) => (
            <li key={index} className="text-sm text-ink-soft leading-relaxed flex gap-2">
              <span className="text-ink-faint shrink-0">·</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
