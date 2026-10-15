import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = BASE_DIR / 'backend'

load_dotenv(BASE_DIR / '.env')


def _get_env_int(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f'Invalid integer value for {name}: {value}') from exc


def _get_env_str(name, default):
    return os.getenv(name, default)


class Settings:
    APP_VERSION = _get_env_str('APP_VERSION', '1.0.0')
    OMAGENOMI_MODE = _get_env_str('OMAGENOMI_MODE', 'auto')
    CLINVAR_DB_PATH = _get_env_str('CLINVAR_DB_PATH', str(BASE_DIR / 'data' / 'clinvar' / 'clinvar.sqlite'))
    DEMO_MANIFEST_PATH = _get_env_str('DEMO_MANIFEST_PATH', str(BASE_DIR / 'data' / 'demo' / 'synthetic_manifest.json'))
    DEMO_LOOKUP_PATH = _get_env_str('DEMO_LOOKUP_PATH', str(BASE_DIR / 'data' / 'demo' / 'demo_lookup.json'))
    DEMO_DNA_PATH = _get_env_str('DEMO_DNA_PATH', str(BASE_DIR / 'data' / 'demo' / 'synthetic_100k_23andme_like_GRCh38.txt'))
    DEMO_SNIPPET_PATH = _get_env_str('DEMO_SNIPPET_PATH', str(BASE_DIR / 'data' / 'demo' / 'quick_demo_snippet_GRCh38.txt'))
    SESSION_ROOT = _get_env_str('SESSION_ROOT', str(BASE_DIR / 'runtime' / 'sessions'))
    SESSION_TTL_HOURS = _get_env_int('SESSION_TTL_HOURS', 2)
    MAX_UPLOAD_MB = _get_env_int('MAX_UPLOAD_MB', 50)
    MAX_PASTE_MB = _get_env_int('MAX_PASTE_MB', 10)
    UPLOAD_CHUNK_BYTES = _get_env_int('UPLOAD_CHUNK_BYTES', 1024 * 1024)
    PASTE_STREAM_CHUNK_BYTES = _get_env_int('PASTE_STREAM_CHUNK_BYTES', 262144)
    DEFAULT_RESOURCE_PROFILE = _get_env_str('DEFAULT_RESOURCE_PROFILE', 'light')

    ULTRALIGHT_PARSE_BATCH = _get_env_int('ULTRALIGHT_PARSE_BATCH', 500)
    ULTRALIGHT_MATCH_BATCH = _get_env_int('ULTRALIGHT_MATCH_BATCH', 500)
    ULTRALIGHT_COOLDOWN_MS = _get_env_int('ULTRALIGHT_COOLDOWN_MS', 750)
    LIGHT_PARSE_BATCH = _get_env_int('LIGHT_PARSE_BATCH', 2000)
    LIGHT_MATCH_BATCH = _get_env_int('LIGHT_MATCH_BATCH', 2000)
    LIGHT_COOLDOWN_MS = _get_env_int('LIGHT_COOLDOWN_MS', 250)
    NORMAL_PARSE_BATCH = _get_env_int('NORMAL_PARSE_BATCH', 5000)
    NORMAL_MATCH_BATCH = _get_env_int('NORMAL_MATCH_BATCH', 5000)
    NORMAL_COOLDOWN_MS = _get_env_int('NORMAL_COOLDOWN_MS', 100)
    HARD_MAX_PARSE_BATCH = _get_env_int('HARD_MAX_PARSE_BATCH', 5000)
    HARD_MAX_MATCH_BATCH = _get_env_int('HARD_MAX_MATCH_BATCH', 5000)
    MAX_ACTIVE_BATCHES = _get_env_int('MAX_ACTIVE_BATCHES', 1)
    SQLITE_CACHE_KB = _get_env_int('SQLITE_CACHE_KB', 8192)
    ALLOWED_ORIGINS = [value.strip() for value in _get_env_str('ALLOWED_ORIGINS', 'http://localhost:5173').split(',') if value.strip()]
    CLINVAR_VCF_URL = _get_env_str('CLINVAR_VCF_URL', 'https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz')
    CLINVAR_VCF_PATH = _get_env_str('CLINVAR_VCF_PATH', '')

    # OmaGenomi Loop (agentic monitoring demo)
    LOOP_EVIDENCE_PATH = _get_env_str('LOOP_EVIDENCE_PATH', str(BASE_DIR / 'data' / 'loop' / 'evidence.json'))
    LOOP_PROFILE_PATH = _get_env_str('LOOP_PROFILE_PATH', str(BASE_DIR / 'data' / 'loop' / 'demo_profile.json'))
    LOOP_STATE_PATH = _get_env_str('LOOP_STATE_PATH', str(BASE_DIR / 'runtime' / 'loop' / 'state.json'))
    # Agenttinen hyvinvointikumppani (support plans): demo policies, demo scenario and the synthetic cohort
    SUPPORT_POLICIES_PATH = _get_env_str('SUPPORT_POLICIES_PATH', str(BASE_DIR / 'data' / 'support' / 'policies.json'))
    SUPPORT_SETUP_PATH = _get_env_str('SUPPORT_SETUP_PATH', str(BASE_DIR / 'data' / 'support' / 'demo_setup.json'))
    SUPPORT_COHORT_PATH = _get_env_str('SUPPORT_COHORT_PATH', str(BASE_DIR / 'runtime' / 'cohort' / 'kohortti.csv'))
    SUPPORT_COHORT_SIZE = _get_env_int('SUPPORT_COHORT_SIZE', 50000)
    # 'off' = template texts only (default), 'anthropic' = try Claude API for texts and falls back to templates
    LOOP_LLM_PROVIDER = _get_env_str('LOOP_LLM_PROVIDER', 'off')
    LOOP_LLM_MODEL = _get_env_str('LOOP_LLM_MODEL', 'claude-opus-5')
    LOOP_LLM_TIMEOUT_SECONDS = _get_env_int('LOOP_LLM_TIMEOUT_SECONDS', 20)
    # Hyvinvointidata: 1 = the clearly synthetic test data may be loaded (demo / development), 0 = real devices only
    HEALTH_DEMO_MODE = _get_env_int('HEALTH_DEMO_MODE', 1)

    # Mieliluotsi – waiting-list companion (the primary application)
    VALITUKI_DATA_DIR = _get_env_str('VALITUKI_DATA_DIR', str(BASE_DIR / 'data' / 'valituki'))
    VALITUKI_STATE_PATH = _get_env_str('VALITUKI_STATE_PATH', str(BASE_DIR / 'runtime' / 'valituki' / 'state.json'))
    # LIVE_AI_MODE = Claude via ANTHROPIC_API_KEY (default); falls back to DEMO_AI_MODE texts when the key is missing or a
    #                call fails
    # DEMO_AI_MODE = deterministic, safe mock texts, needs no API key
    VALITUKI_AI_MODE = _get_env_str('VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    VALITUKI_AI_MODEL = _get_env_str('VALITUKI_AI_MODEL', 'claude-opus-5')
    VALITUKI_AI_TIMEOUT_SECONDS = _get_env_int('VALITUKI_AI_TIMEOUT_SECONDS', 30)
    # Who answers in LIVE_AI_MODE: 'anthropic' = Claude (default), 'openai' = any OpenAI-compatible server such as vLLM on
    # an AMD GPU. VALITUKI_OPENAI_MODEL may be left empty: the server's first model is used.
    VALITUKI_AI_PROVIDER = _get_env_str('VALITUKI_AI_PROVIDER', 'anthropic')
    VALITUKI_OPENAI_BASE_URL = _get_env_str('VALITUKI_OPENAI_BASE_URL', '')
    VALITUKI_OPENAI_MODEL = _get_env_str('VALITUKI_OPENAI_MODEL', '')
    VALITUKI_OPENAI_LABEL = _get_env_str('VALITUKI_OPENAI_LABEL', 'AMD GPU')
    # The earlier OmaGenomi features (DNA analysis, genetic-risk loop, care plans, Apple Health) are kept in the
    # repository but hidden from the product. 1 = mount their API routes again.
    LEGACY_FEATURES_ENABLED = _get_env_int('LEGACY_FEATURES_ENABLED', 0)

    def validate(self):
        assert self.VALITUKI_AI_MODE in {'DEMO_AI_MODE', 'LIVE_AI_MODE'}
        assert self.VALITUKI_AI_PROVIDER in {'anthropic', 'openai'}
        assert self.OMAGENOMI_MODE in {'auto', 'demo', 'clinvar'}
        assert self.DEFAULT_RESOURCE_PROFILE in {'ultralight', 'light', 'normal'}
        assert self.MAX_UPLOAD_MB > 0
        assert self.MAX_PASTE_MB > 0
        assert self.UPLOAD_CHUNK_BYTES > 0
        assert self.PASTE_STREAM_CHUNK_BYTES > 0
        assert self.SESSION_TTL_HOURS > 0
        assert self.MAX_ACTIVE_BATCHES >= 1


settings = Settings()
settings.validate()
