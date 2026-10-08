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
const STATUS: Record<FilmReviewReport['status'], string> = {
  passed: 'Met the rubric on sampled frames',
  needs_review: 'Below the bar — review before publishing',
  unavailable: 'Visual review unavailable',
  reviewed: 'Reviewed (legacy check)',
};

export function FilmReview({ report }: { report: FilmReviewReport }) {
  const review = report.final?.review;
  const scores = report.final?.scores;
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
            const score: number | undefined = scores[axis];
            return (
              <li key={axis} className={typeof score === 'number' && score >= 8 ? 'ok' : 'low'}>
                <span>{LABELS[axis]}</span>
                {typeof score === 'number' && (
                  <meter min={1} max={10} low={7.9} optimum={10} value={score} />
                )}
                <b>{score ?? '–'}</b>
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
