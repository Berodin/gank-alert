import os

# gank_api.config.Settings() reads these at import time -- must be set
# before anything imports gank_api.* for the first time, so this has to
# happen in conftest.py (loaded before test module collection) rather than
# in a fixture.
os.environ.setdefault("GANK_EVE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GANK_EVE_REDIRECT_URI", "http://127.0.0.1:8000/auth/eve/callback")
