import type { Finding } from './types';

export const labels: Record<string, string> = {
  same_image: 'Same image',
  likely_copy: 'Likely copy',
  visually_similar: 'Visual candidate',
  unverified: 'Unverified',
  owner_confirmed: 'Owner-confirmed match',
  owner_rejected: 'Owner-rejected match',
  unreviewed: 'Needs review',
  confirmed_match: 'Match confirmed',
  authorized: 'Authorized',
  not_a_match: 'Not a match',
  investigate: 'Investigate',
  recorded_permission: 'Permission recorded',
  scope_requires_review: 'Check permission scope',
  unknown: 'Permission unknown',
  same_character: 'Same character',
  different_character: 'Different character',
  uncertain: 'Uncertain',
};
export const shortDate = (value: string) =>
  new Date(value).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
export const needsReview = (f: Finding) =>
  f.payload.review.decision === 'unreviewed' &&
  f.payload.match.kind !== 'owner_rejected' &&
  f.payload.permission.status !== 'recorded_permission';
