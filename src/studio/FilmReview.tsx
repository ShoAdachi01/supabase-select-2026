import { AXES, type FilmReviewReport, type ReviewFinding } from './types';

const LABELS: Record<(typeof AXES)[number], string> = {
  readability: 'Readability',
  canvas: 'Canvas',
  motion: 'Motion',
  pacing: 'Pacing',
  typography: 'Type',
  continuity: 'Continuity',
  specificity: 'Specificity',
};
const STATUS = {
  passed: 'Met the rubric on sampled frames',
  needs_review: 'Below the bar — review before publishing',
  unavailable: 'Visual review unavailable',
};

export function FilmReview({ report }: { report: FilmReviewReport }) {
  // The last scored pass that was not a rejected revision describes the film that shipped.
  const last = [...report.passes].reverse().find((p) => p.review && !p.rejected_revision?.length);
  const review = last?.review;
  const scores = last?.scores;
  const findings: ReviewFinding[] = review
    ? [...(review.blocking ?? []), ...AXES.flatMap((axis) => review[axis]?.findings ?? [])]
    : [];
  return (
    <section className={`film-review ${report.status}`} aria-label="Film review">
      <header>
        <strong>{STATUS[report.status] ?? STATUS.unavailable}</strong>
        <small>
          {report.revision_count} revision{report.revision_count === 1 ? '' : 's'}
        </small>
      </header>
      {scores && (
        <ul className="film-review-scores">
          {AXES.map((axis) => {
            const score = scores[axis] ?? 0;
            return (
              <li key={axis} className={score >= 8 ? 'ok' : 'low'}>
                <span>{LABELS[axis]}</span>
                <meter min={1} max={10} low={7.9} optimum={10} value={score} />
                <b>{scores[axis] ?? '–'}</b>
              </li>
            );
          })}
        </ul>
      )}
      {findings.length > 0 && (
        <ol className="film-review-findings">
          {findings.map((f, i) => (
            <li key={i}>
              <span>
                Shot {f.shot + 1} · {f.time.toFixed(1)}s
              </span>{' '}
              {f.problem} <em>{f.change}</em>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
