// Ported 1:1 from dashboard/game_endings_view.py's _END_TYPE_LABELS and
// _RESIGN_REASON_LABELS -- kept in sync by hand, same accepted
// duplication risk as THEME/navConfig. not_analyzed has no Streamlit
// equivalent (that page excludes it from its reason chart entirely);
// added here since the Ending Tree icicle shows it as its own leaf.
export const END_TYPE_LABELS: Record<string, string> = {
  resignation: 'Resignation',
  time_forfeit: 'Time forfeit',
  checkmate: 'Checkmate',
  draw_repetition: 'Repetition draw',
  abandoned: 'Abandoned',
  insufficient_material: 'Insufficient material',
  draw_agreement: 'Draw by agreement',
  stalemate: 'Stalemate',
  draw_50_move_rule: '50-move rule',
  unknown: 'Unknown',
}

export const RESIGNATION_REASON_LABELS: Record<string, string> = {
  hung_piece: 'Hung a piece',
  faced_mate: 'Faced a forced mate',
  time_pressure: 'Time pressure',
  other: 'Other / gradual decline',
  not_analyzed: 'Not yet analyzed',
}
