/**
 * Pixel AI — Store Purchase Handler (Cloudflare Pages Function)
 *
 * Called when a customer purchases Pixel AI Pro from the web store.
 * Uses X-Issue-Secret to call Pixel AI's /api/license/issue endpoint
 * (mirrors finance-kit pattern).
 *
 * Environment variables (set in Cloudflare dashboard):
 *   PIXEL_API_URL       — https://your-pixel-service-xxx-uc.a.run.app
 *   PIXEL_ISSUE_SECRET  — Shared HMAC secret for /api/license/issue
 *   STORE_API_KEY       — Shared secret for verifying frontend requests
 *   PIXEL_PRO_PRICE_USDC — Price for Pro plan (default: 29)
 */

const PRICES = { pro: 29, enterprise: 99 };

export async function onRequestPost(context) {
  const { request, env } = context;

  if (request.method === 'OPTIONS') {
    return new Response(null, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Store-Key',
      },
    });
  }

  try {
    const body = await request.json();
    const { plan, email, source } = body;

    if (!plan) {
      return json({ success: false, error: 'plan is required' }, 400);
    }
    if (!email || !email.includes('@')) {
      return json({ success: false, error: 'Valid email required' }, 400);
    }

    const storeKey = request.headers.get('X-Store-Key');
    if (storeKey !== env.STORE_API_KEY) {
      return json({ success: false, error: 'Forbidden' }, 403);
    }

    const tier = plan.toLowerCase();
    if (!PRICES[tier]) {
      return json({ success: false, error: `Unknown plan: ${plan}` }, 400);
    }

    // Call Pixel AI API to issue a license key (finance-kit style)
    const pixelUrl = env.PIXEL_API_URL || 'http://localhost:8642';
    const orderId = `store_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    const issueRes = await fetch(`${pixelUrl}/api/license/issue`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Issue-Secret': env.PIXEL_ISSUE_SECRET,
      },
      body: JSON.stringify({ email, tier, order_id: orderId }),
    });

    if (!issueRes.ok) {
      const err = await issueRes.text();
      return json({ success: false, error: `License issue failed: ${err}` }, 502);
    }

    const licenseData = await issueRes.json();

    return json({
      success: true,
      api_key: licenseData.token,
      tier: licenseData.tier,
      email: licenseData.email,
      email_sent: licenseData.email_sent,
      order_id: orderId,
      message: `Pixel AI ${tier.charAt(0).toUpperCase() + tier.slice(1)} plan activated!`,
    });
  } catch (e) {
    return json({ success: false, error: e.message }, 500);
  }
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
    },
  });
}
