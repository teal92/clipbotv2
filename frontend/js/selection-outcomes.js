// Selection outcomes are completed reviews, not processing failures.
const OUTCOMES=Object.freeze({
 analysis_no_moment:{title:'No moment found',help:'Davey completed this review without finding a complete clip candidate.'},
 analysis_below_threshold:{title:'Below score setting',help:'The candidate did not meet the score setting used for this review.'},
 analysis_length_settings:{title:'Outside clip length setting',help:'The candidate did not fit the clip length setting used for this review.'},
 not_selected:{title:'Earlier selection outcome',help:'This earlier review did not produce a clip. Its specific selection reason was not recorded.'}
});
export const selectionOutcome=code=>Object.hasOwn(OUTCOMES,code)?OUTCOMES[code]:null;
export const isSelectionOutcome=job=>job.stage==='failed'&&Boolean(selectionOutcome(job.errorCode));
