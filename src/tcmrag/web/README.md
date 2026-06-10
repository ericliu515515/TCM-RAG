# Streamlit Web App Module Map

This package keeps the Streamlit app reviewable by separating storage, source
loading, styling, and UI wiring.

- `config.py`: project paths, app settings, threshold clamping, and `.env` setup.
- `documents.py`: uploaded PDF source manifests, chunk loading, duplicate-upload
  detection, and PDF rendering helpers.
- `chat_sessions.py`: saved-chat JSON cleaning, titles, reads, writes, and lists.
- `styles.py`: CSS used by the Streamlit UI.

The root `app.py` remains the Streamlit entrypoint. It should mostly contain UI
state and rendering functions; file parsing and persistence should live in this
package.
