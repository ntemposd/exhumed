// ProgressTrack is a minimal visual primitive for percentage-based indicators.
type ProgressTrackProps = {
  value: number;
  max?: number;
  slim?: boolean;
  signal?: boolean;
};

export function ProgressTrack({ value, max = 100, slim = false, signal = false }: ProgressTrackProps) {
  const boundedWidth = max > 0 ? Math.max(0, Math.min((value / max) * 100, 100)) : 0;
  const trackClassName = `progressTrack ${slim ? "progressTrackSlim" : ""}`.trim();
  const fillClassName = `progressFill ${signal ? "progressFillSignal" : ""}`.trim();

  return (
    <div className={trackClassName}>
      <div className={fillClassName} style={{ width: `${boundedWidth}%` }} />
    </div>
  );
}