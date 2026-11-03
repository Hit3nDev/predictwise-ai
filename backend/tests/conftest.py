import os, sys, tempfile

# Run every test inside a throwaway working directory so the real
# predictwise.db / uploads / artifacts folders are never touched.
_tmp = tempfile.mkdtemp(prefix="pw-test-")
os.chdir(_tmp)
# A developer's real backend/.env (API keys) must not change what the tests see.
os.environ.setdefault("PW_SKIP_ENV_FILE", "1")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
