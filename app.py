"""Flask entry point for Vercel."""

from werkzeug.middleware.proxy_fix import ProxyFix

from backend.app import create_app

app = create_app()
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1)
