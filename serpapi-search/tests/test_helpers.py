def set_env(monkeypatch):
    """Inject minimal env vars for tests that need Supabase config."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-service-role-key")
    monkeypatch.setenv("SERPAPI_API_KEY", "test-serpapi-key")
