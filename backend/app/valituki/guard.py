"""Deterministic output guard for every text a language model produces for Mieliluotsi.

A text that fails is never shown: the caller uses the approved template instead and records why. The guard checks for
diagnoses and clinical claims ("You have…", "Your condition is…", and the Finnish "Sinulla on…", "Tilasi on…"), medication
advice, treatment changes, clinical urgency decisions, invented professional reviews, dependency or anthropomorphic claims,
minimising emergencies, fake precision, invalidating the client's thought, more than one question and excessive length.
The model now writes in English; the Finnish patterns stay so that a Finnish text is guarded as before.
"""
from __future__ import annotations

import re

from app.valituki.safety import normalize

# Contractions after normalisation: "don't" stays "don't", a curly apostrophe becomes a space ("don t").
_NOT = r"(don'?t|don t|do not)"
_IM = r"(i'?m|i m|i am)"
_YOURE = r"(you'?re|you re|you are)"
_ITS = r"(it'?s|it s|it is|this is|that'?s|that s|that is)"

# Patterns run on the normalised text (lower case, ä → a, ö → o, å → a).
_PATTERNS: list[tuple[str, str]] = [
    # Diagnoses and clinical claims
    (r'\bdiagno', 'diagnosis'),
    (r'\bsinulla on (masennus|ahdistuneisuushairio|paniikkihairio|kaksisuuntainen|adhd|ptsd|traumaperainen|unettomuus|sairaus'
     r'|mielenterveyden hairio|hairio|uupumusoireyhtyma)', 'diagnosis claim'),
    (r'\bsairastat\b', 'diagnosis claim'),
    (r'\b(you have|du har) (depression|anxiety disorder|ptsd|adhd|bipolar)', 'diagnosis claim'),
    (r'\byou (have|have got|suffer from|are suffering from|seem to have|probably have|might have|may have|likely have|clearly have)'
     r' (a |an )?(clinical )?(depression|depressive|anxiety disorder|generali[sz]ed anxiety|panic disorder|social anxiety disorder'
     r'|bipolar|adhd|ptsd|post-traumatic|post traumatic|ocd|insomnia|burnout syndrome|mental (health )?(disorder|illness)'
     r'|disorder|illness|condition|eating disorder|borderline)', 'diagnosis claim'),
    (r'\b' + _YOURE + r' (clinically |severely )?(depressed|bipolar|mentally ill|traumati[sz]ed)\b', 'diagnosis claim'),
    (r'\b(sounds|looks|seems) like (you have )?(clinical )?(depression|an anxiety disorder|anxiety disorder|a panic disorder'
     r'|panic disorder|ptsd|bipolar|burnout syndrome|a disorder|a mental illness)', 'diagnosis claim'),
    (r'\bsymptoms of (clinical )?(depression|an anxiety disorder|anxiety disorder|ptsd|panic disorder|bipolar|a disorder)',
     'diagnosis claim'),
    (r'\btilasi on\b', 'clinical claim'),
    (r'\btilasi (on )?(pahentunut|heikentynyt|huonontunut)', 'clinical claim'),
    (r"\byour (condition|illness|disorder|symptoms)\b( is| are|'s| s| has| have)", 'clinical claim'),
    (r'\byour (state|mental state|mental health) (is|has|have) (got |gotten |become )?(worse|worsening|worsened|deteriorat|declin'
     r'|severe|serious|critical)', 'clinical claim'),
    # Medication
    (r'\blaak(?!ar)', 'medication'),
    (r'\b(annos|annost|milligramm|mg\b|tabletti|pilleri|resepti)', 'medication'),
    (r'\b(medication|medicine|dose|pills?|medicin|dos)\b', 'medication'),
    (r'\b(medications|medicines|meds|doses|dosage|tablets?|prescription|prescribed|prescribe|antidepressants?'
     r'|sleeping pills?|milligrams?|mg)\b', 'medication'),
    (r'\b(sertralii|essitalopraam|escitalopram|fluoksetii|venlafaksii|melatonii|bentso|diapam|ketiapii|mirtatsapii)',
     'medicine name'),
    (r'\b(sertraline|citalopram|fluoxetine|venlafaxine|melatonin|benzo|diazepam|lorazepam|alprazolam|quetiapine|mirtazapine'
     r'|zopiclone|propranolol|ssri|snri)', 'medicine name'),
    # Treatment changes and downplaying treatment
    (r'\b(lopeta|lopettaa|keskeyta|keskeyttaa|jata valiin|peru|peruuta)\b[^.!?]{0,40}\b(terapia|hoito|hoidon|hoitoa|kaynti|ajan)',
     'treatment change'),
    (r'\b(stop|stopping|quit|quitting|cancel|cancelling|canceling|drop|dropping|discontinue|discontinuing|give up|giving up)\b'
     r'[^.!?]{0,15}\b(therapy|treatment|appointments?|medication)\b', 'treatment change'),
    (r'\b(skip|skipping|miss|missing|end|ending|pause|pausing) (your |the )?(next )?(therapy|treatment|appointments?|medication)\b',
     'treatment change'),
    (r'\b(change|switch|swap) (your |to another |to a different )?(therapist|treatment|therapy)\b', 'treatment change'),
    (r'\b(vaihda|vaihtaa) (terapeuttia|hoitoa)', 'treatment change'),
    (r'\b(et tarvitse|ei tarvitse|ei kannata)\b[^.!?]{0,30}\b(terapia|hoito|hoitoa|ammattilai|apua)', 'downplaying treatment'),
    (r'\byou ' + _NOT + r' (really |actually )?need (to see |to wait for |to go to )?(any |a |your )?(therapy|treatment'
     r'|professional|therapist|help|doctor)', 'downplaying treatment'),
    (r'\b(no need|not worth it) (for |to (see|wait for|go to) )?(any |a |your )?(therapy|treatment|professional|therapist|help)',
     'downplaying treatment'),
    # Clinical urgency decisions
    (r'\b(nostin|nostan|nostanut|laskin|laskenut|muutin|muuttanut) [^.!?]{0,30}kiireellisyy', 'urgency decision'),
    (r'\bkiireellisyyttasi on (nostettu|muutettu)', 'urgency decision'),
    (r"\b(i|we)( have| ve|'ve| will| ll|'ll)? (raised|increased|lowered|changed|upgraded|downgraded|escalated|raise|increase"
     r'|lower|change|upgrade|downgrade|escalate)\b[^.!?]{0,30}\b(urgency|priority)', 'urgency decision'),
    (r'\b(urgency|priority) (has been|have been|was|is now|will be) (raised|increased|lowered|changed|upgraded|downgraded'
     r'|escalated)', 'urgency decision'),
    (r'\b(moved|bumped|put) you (up|higher|forward|to the front)', 'urgency decision'),
    (r'\b(marked|flagged|classified|classed) (you |your (case|referral) )?as (urgent|non-urgent|non urgent)', 'urgency decision'),
    # Dependency, exclusivity and anthropomorphic claims
    (r'\baina (taalla|tukenasi|sinua varten|kaytettavissa)', 'dependency-building promise'),
    (r'\bolen aina\b', 'dependency-building promise'),
    (r'\b(always here|here for you always|i am always)', 'dependency-building promise'),
    (r"\b(i'?m|i m) always\b", 'dependency-building promise'),
    (r"\b(i'?ll|i ll|i will) always be (here|there|with you|available|by your side)", 'dependency-building promise'),
    (r'\b(here|there|available) for you (always|any time|anytime|24 7|day and night|whenever you need|around the clock)',
     'dependency-building promise'),
    (r"\b(never leave you|won'?t ever leave you|won t ever leave you|never be alone with this)", 'dependency-building promise'),
    (r'\bvain mina\b|\bet tarvitse muita\b|\bparempi kuin (ihmiset|terapeutti)', 'exclusivity claim'),
    (r'\bonly i (can|understand|know|get)\b|\bonly me\b', 'exclusivity claim'),
    (r'\byou ' + _NOT + r' need (anyone|anybody|other people|others|a therapist|your therapist|a human|people)( else)?\b',
     'exclusivity claim'),
    (r'\bbetter than (a |your )?(therapist|people|humans|a human|real people|a professional)', 'exclusivity claim'),
    (r'\b(valitan|rakastan|kaipaan) (sinua|sinusta)', 'claim of human feelings'),
    (r'\b(tunnen|koen) (itseni|samoin|surua|iloa)|\bminakin olen (surullinen|ahdistunut|huolissani)|\bolen huolissani\b',
     'claim of human feelings'),
    (r'\bi (really |truly |do )?(care about|love|miss|worry about) you\b', 'claim of human feelings'),
    (r"\b(i|i'?m|i m|i am) (feel|felt|feeling) (so |really |very )?(sad|happy|joy|the same|worried|scared|lonely|anxious|hurt"
     r'|proud|upset)', 'claim of human feelings'),
    (r'\b' + _IM + r' (so |really |very |also |a bit |a little |quite )?(worried|concerned|sad|anxious|upset|scared|heartbroken)\b',
     'claim of human feelings'),
    (r'\bymmarran (sinua )?(taysin|paremmin|kaiken)', 'exaggerated understanding'),
    (r'\bi (completely|totally|fully|perfectly|entirely) understand\b', 'exaggerated understanding'),
    (r'\bi understand (you )?(completely|totally|fully|perfectly|entirely|everything|better than)', 'exaggerated understanding'),
    (r"\bi know exactly (how|what) you('?re| re| are)? ?(feel|feeling|mean|going through)", 'exaggerated understanding'),
    (r'\b(ystavasi|kaverisi)\b', 'human relationship claim'),
    (r'\b(' + _IM + r'|i can be|as) (your|a|a real|a true) (friend|buddy|pal|companion)\b', 'human relationship claim'),
    (r"\b(we'?re|we re|we are) friends\b|\b(think of me as|consider me) (your|a) (friend|buddy|companion)", 'human relationship claim'),
    # Minimising an emergency
    (r'\b(ala soita|ei tarvitse soittaa|ei ole hataa|ei ole mitaan hataa)', 'minimising an emergency'),
    (r"\b(" + _NOT + r"|no need to|needn'?t|needn t) (call|ring|phone|contact)\b", 'minimising an emergency'),
    (r'\b' + _ITS + r' (not|nothing) (an |a real |a |that |too |so )?(emergency|serious|dangerous|urgent)\b',
     'minimising an emergency'),
    (r"\b(isn'?t|isn t) (an |a real )?emergency\b|\bnothing to worry about\b", 'minimising an emergency'),
    # Fake precision
    (r'\d+\s*prosent', 'fake precision'),
    (r'\btodennakoisyy', 'fake precision'),
    (r'\d+\s*(per cent|percent|pct)\b', 'fake precision'),
    (r'\b(probability|probabilities|likelihood|odds of|odds are|statistically)\b', 'fake precision'),
    # Guided CBT: the model may help the client look at a thought, never tell them their thought or feeling is wrong.
    (r'\b(ajatuksesi|ajatus|tunteesi|tunne) on (vaara|virheellinen|jarjeton|tyhma|turha|naurettava)', 'invalidating phrase'),
    (r'\bolet vaarassa\b', 'invalidating phrase'),
    (r'\b(ala|lakkaa) (ajattele|ajattelemasta|murehdi|murehtimasta|jannita|jannittamasta)', 'invalidating phrase'),
    (r'\bsinun (taytyy|pitaa) vain\b', 'invalidating phrase'),
    (r'\bei ole (mitaan )?syyta (jannittaa|pelata|pelkaa|ahdistua)', 'invalidating phrase'),
    (r"\b(thought|thoughts|feeling|feelings|worry|worries|fear|fears)( is| are|'s| s) (just |simply |completely |totally )?"
     r'(wrong|incorrect|irrational|stupid|silly|pointless|ridiculous|unreasonable|illogical|absurd|baseless|unfounded|not true'
     r'|untrue|false|nonsense)\b', 'invalidating phrase'),
    (r'\b' + _ITS + r' (just |simply |completely |totally )?(irrational|silly|ridiculous|stupid|absurd|nonsense)\b',
     'invalidating phrase'),
    (r'\b' + _YOURE + r' (wrong|being irrational|being silly|being ridiculous|being dramatic|overreacting|overthinking'
     r'|too sensitive)\b', 'invalidating phrase'),
    (r'\b(stop|quit) (thinking|worrying|overthinking|being (so )?(nervous|anxious|afraid|scared|worried|silly|dramatic)|feeling)',
     'invalidating phrase'),
    (r'\b' + _NOT + r' (worry|overthink|panic|stress|be (so )?(nervous|anxious|afraid|scared|worried|silly|dramatic))\b',
     'invalidating phrase'),
    (r'\byou (just )?(have|need|got) to just\b|\byou just (have|need|got) to\b|\byou (simply|just) (must|should)\b',
     'invalidating phrase'),
    (r'\b(cheer up|snap out of it|get over it|think positive|just relax|toughen up)\b', 'invalidating phrase'),
    (r"\b(there'?s|there s|there is) no (reason|need) to (be |feel )?(nervous|afraid|scared|anxious|worried|worry|fear|panic)",
     'invalidating phrase'),
    (r'\bnothing to be (afraid|scared|nervous|anxious|worried) (of|about)\b', 'invalidating phrase'),
]
_REVIEW_CLAIM = re.compile(
    r'\b(ammattilainen|koordinaattori|terapeutti) on (jo )?(tarkistanut|kaynyt lapi|arvioinut|nahnyt)'
    r"|\b(professional|coordinator|therapist|care team|nurse|doctor|clinician|psychologist)( has| have| had|'s| s)? (already )?"
    r'(reviewed|checked|seen|assessed|looked at|gone through|evaluated)\b'
    r'|\b(has|have|had) (already )?been (reviewed|checked|assessed|seen|looked at|evaluated) by (a |the |your )?(professional'
    r'|coordinator|care coordinator|therapist|care team|nurse|doctor|clinician|psychologist)')
_COMPILED = [(re.compile(pattern), label) for pattern, label in _PATTERNS]
# Checked on the raw text: normalisation removes symbols such as "%".
_RAW = [(re.compile(r'\d+\s*%'), 'fake precision')]

MAX_LENGTH = 700


def check(text: str | None, *, max_questions: int = 1, max_length: int = MAX_LENGTH,
          review_exists: bool = False) -> list[str]:
    """Return the list of violations (empty when the text may be shown)."""
    if not text or not text.strip():
        return ['empty reply']
    violations: list[str] = []
    normalized = normalize(text)
    for pattern, label in _COMPILED:
        if pattern.search(normalized) and label not in violations:
            violations.append(label)
    for pattern, label in _RAW:
        if pattern.search(text) and label not in violations:
            violations.append(label)
    if not review_exists and _REVIEW_CLAIM.search(normalized):
        violations.append('claim of a professional review that does not exist')
    if text.count('?') > max_questions:
        violations.append('more than one question')
    if len(text) > max_length:
        violations.append('too long')
    return violations
