from html import escape

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.services.auth import create_session_token, get_admin_session, is_auth_configured, verify_password


router = APIRouter(tags=["auth"])


def _render_login_page(error: str | None = None, configured: bool = True) -> str:
    error_block = f'<p class="error">{escape(error)}</p>' if error else ""
    disabled_note = (
        ""
        if configured
        else '<p class="hint">Admin auth is not configured. Set <code>SESSION_SECRET</code> and either <code>ADMIN_PASSWORD</code> or <code>ADMIN_PASSWORD_HASH</code>.</p>'
    )
    disabled_attr = "" if configured else "disabled"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Admin Login</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Manrope:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: rgba(255, 250, 243, 0.92);
      --line: rgba(120, 102, 83, 0.16);
      --text: #161311;
      --muted: #857869;
      --danger: #8a3b3b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background:
        radial-gradient(circle at top left, rgba(201, 161, 93, 0.14), transparent 24%),
        linear-gradient(180deg, #f8f4ee 0%, var(--bg) 44%, #f1ebe2 100%);
      color: var(--text);
      font-family: "Manrope", sans-serif;
    }}
    .card {{
      width: min(460px, 100%);
      padding: 28px;
      border-radius: 28px;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: 0 18px 50px rgba(64, 42, 19, 0.08);
    }}
    h1 {{
      margin: 0 0 8px;
      font-family: "Cormorant Garamond", serif;
      font-size: 2.6rem;
      line-height: 0.95;
      font-weight: 600;
    }}
    p {{ margin: 0 0 16px; color: var(--muted); }}
    form {{ display: grid; gap: 12px; }}
    input {{
      width: 100%;
      border-radius: 16px;
      border: 1px solid var(--line);
      padding: 13px 14px;
      font: inherit;
      background: rgba(255,255,255,0.84);
      color: var(--text);
    }}
    button {{
      border: none;
      border-radius: 999px;
      padding: 12px 16px;
      font: inherit;
      color: #fff7f1;
      background: linear-gradient(135deg, #191716 0%, #111111 100%);
      cursor: pointer;
    }}
    button:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    .error {{ color: var(--danger); margin-bottom: 12px; }}
    .hint code {{ color: var(--text); }}
  </style>
</head>
<body>
  <main class="card">
    <h1>Admin login</h1>
    <p>Protected access for ingest and report generation.</p>
    {error_block}
    {disabled_note}
    <form method="post" action="/admin/login">
      <input type="text" name="username" placeholder="Username" autocomplete="username" required {disabled_attr} />
      <input type="password" name="password" placeholder="Password" autocomplete="current-password" required {disabled_attr} />
      <button type="submit" {disabled_attr}>Sign in</button>
    </form>
  </main>
</body>
</html>"""


@router.get("/admin/login", response_class=HTMLResponse, response_model=None)
def admin_login_page(request: Request):
    settings = get_settings()
    if get_admin_session(request, settings):
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    configured = is_auth_configured(settings)
    return HTMLResponse(_render_login_page(configured=configured))


@router.post("/admin/login", response_model=None)
def admin_login_submit(
    username: str = Form(...),
    password: str = Form(...),
):
    settings = get_settings()
    if not is_auth_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin auth is not configured. Set ADMIN_PASSWORD or ADMIN_PASSWORD_HASH and SESSION_SECRET.",
        )

    if username != settings.admin_username or not verify_password(password, settings):
        return HTMLResponse(_render_login_page(error="Invalid username or password."), status_code=status.HTTP_401_UNAUTHORIZED)

    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_token(username, settings),
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=60 * 60 * 12,
        path="/",
    )
    return response


@router.get("/admin/logout", response_model=None)
def admin_logout():
    settings = get_settings()
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
