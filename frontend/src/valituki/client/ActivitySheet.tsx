import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { ClockIcon, InfoIcon } from '../icons';
import { Pill, Scale5, Sheet, SourceNote } from '../components/ui';
import { useClientUI } from './ClientApp';

/** An approved activity: steps from the library as written; only the short introduction may be personalised. */
export default function ActivitySheet({ activityId, onClose }: { activityId: string; onClose: () => void }) {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const [rating, setRating] = useState<number | null>(null);
  const [done, setDone] = useState(false);
  const activity = view.meta.library.activities.find((a) => a.id === activityId);
  if (!activity) return null;
  const today = client.today && client.today.id === activityId ? client.today : null;

  async function complete() {
    const result = await run((s) => api.completeActivity(s, client.id, activityId, rating),
      () => (rating && rating >= 4 ? 'Saved as something that helps you – your Therapy Fit Profile was updated.' : 'Exercise saved. Thank you!'));
    if (result !== null) onClose();
  }

  return (
    <Sheet title={activity.title} onClose={onClose} footer={done ? (
      <button type="button" className="btn btn-primary btn-block" disabled={busy} onClick={complete}>Save</button>
    ) : (
      <div className="row-gap row-stretch">
        <button type="button" className="btn btn-quiet" disabled={busy}
          onClick={async () => { await run((s) => api.skipActivity(s, client.id, activityId), () => 'Exercise skipped – that is always fine.'); onClose(); }}>
          Skip this exercise
        </button>
        <button type="button" className="btn btn-primary" onClick={() => setDone(true)}>I did the exercise</button>
      </div>
    )}>
      <p className="activity-meta"><ClockIcon size={15} /> {activity.estimatedDuration} min <Pill tone="ok">Approved exercise v{activity.version}</Pill></p>
      {today ? (
        <div className="activity-intro"><p>{today.intro}</p><SourceNote source={today.introSource} /></div>
      ) : <p>{activity.purpose}</p>}
      {done ? (
        <>
          <p className="q">How helpful was the exercise?</p>
          <Scale5 name="How helpful was the exercise?" value={rating} onChange={setRating}
            labels={{ '1': 'Not at all', '2': 'A little', '3': 'Somewhat', '4': 'Helpful', '5': 'Very helpful' }} />
        </>
      ) : (
        <>
          <ol className="steps">{activity.steps.map((step) => <li key={step}>{step}</li>)}</ol>
          <p className="caution"><InfoIcon size={15} /> {activity.caution}</p>
          <p className="muted small">{activity.sourcePlaceholder} · Approved {activity.approvedAt}</p>
        </>
      )}
    </Sheet>
  );
}
