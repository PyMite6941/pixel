# Pixel AI — Web Store

Cloudflare Pages site + Workers function for selling Pixel AI subscriptions.

## Deploy

```bash
# Set environment secrets
npx wrangler secret put PIXEL_API_URL
npx wrangler secret put PIXEL_API_KEY
npx wrangler secret put STORE_API_KEY

# Deploy
npm run deploy
```

## Environment Variables

| Variable | Description |
|---|---|
| `PIXEL_API_URL` | Pixel AI Cloud Run URL (e.g. `https://pixel-xxx-uc.a.run.app`) |
| `PIXEL_API_KEY` | Pixel AI admin API key with code generation permission |
| `STORE_API_KEY` | Shared secret between store frontend and worker |
