import { useValituki } from '../context';
import { Pill, Synthetic } from '../components/ui';

export default function Directory() {
  const { view } = useValituki();
  const rows = view.professional.directory;
  const weights = view.meta.matching.weights;
  return (
    <div className="directory-page">
      <section className="card">
        <h2 className="card-title-lg">Therapist directory and capacity</h2>
        <Synthetic>The demo's fictional therapists. Free appointments come from the TherapistDirectoryAdapter's calendar sync (mock).</Synthetic>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th scope="col">Therapist</th><th scope="col">Specialties</th><th scope="col">Approach</th><th scope="col">Languages</th>
                <th scope="col">Sessions</th><th scope="col">Capacity</th><th scope="col">Next free appointment</th></tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id} className={t.active ? '' : 'row-muted'}>
                  <td><strong>{t.name}</strong><span className="row-sub">{t.role}</span></td>
                  <td className="small">{t.specialties.join(', ')}</td>
                  <td className="small">{t.workingStyle}<span className="row-sub">{t.approaches.join(', ')}</span></td>
                  <td className="small">{t.languages.join(', ')}</td>
                  <td className="small">{t.formats.join(' · ')}<span className="row-sub">{t.availableTimes.join(', ')}</span></td>
                  <td>{t.active ? (
                    <Pill tone={t.currentCapacity >= t.maxCapacity ? 'warn' : 'ok'}>{t.currentCapacity}/{t.maxCapacity}</Pill>
                  ) : <Pill tone="neutral">{t.inactiveReason}</Pill>}</td>
                  <td className="small">{t.nextAvailableSlot ?? (t.currentCapacity >= t.maxCapacity ? 'No places' : '–')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card">
        <h2 className="card-title">Matching weights (editable: data/valituki/matching_config.json)</h2>
        <div className="weights">
          {Object.entries(weights).map(([key, value]) => (
            <div key={key} className="weight"><span>{WEIGHT_LABELS[key] ?? key}</span><strong>{value}%</strong></div>
          ))}
        </div>
        <p className="muted small">{view.meta.matching.note}</p>
        <h3 className="card-title">Integration points (mock implementations in the demo)</h3>
        <ul className="adapters">
          {view.meta.adapters.map((a) => <li key={a.name}><code>{a.name}</code> – {a.production}</li>)}
        </ul>
      </section>
    </div>
  );
}

const WEIGHT_LABELS: Record<string, string> = {
  goalCompetence: 'Goals and expertise', workingStyle: 'Way of working', userPreferences: 'Own wishes',
  languageAccessibility: 'Language and accessibility', availabilityContinuity: 'Availability and continuity', logistics: 'Logistics',
};
