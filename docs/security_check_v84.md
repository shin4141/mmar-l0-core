# MMAR Security Check v84

- API keys stay server-side only. No frontend code reads `XAI_API_KEY`, and `.env` is ignored by git.
- X import accepts only `https://x.com/.../status/...` URLs on the backend.
- AI-visible text is rendered via `textContent` or escaped before HTML interpolation.
- External source links are validated before being assigned to `href`.
- Battle creation from X prevents double-submit while a request is in flight.
- User-facing X import failures are sanitized; provider/internal details are not shown in the UI.
