# LUCIFER — Voice Assistant Frontend (Vercel)

Static web UI for the Lucifer voice assistant. Talks to the backend (Cloudflare tunnel) at `API_BASE` in `app.js`.

## Deploy to Vercel
1. Push this `frontend/` folder to a GitHub repo.
2. Vercel → New Project → import repo → Framework: **Other** → Deploy.
3. Edit `API_BASE` in `app.js` to your Cloudflare tunnel URL.

No build step needed (plain HTML/CSS/JS).
