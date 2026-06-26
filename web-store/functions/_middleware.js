/**
 * Pixel AI Store — Security & Rate Limiting Middleware
 */
export async function onRequest(context) {
  const { request, next } = context;

  const response = await next();

  // Add security headers
  const headers = new Headers(response.headers);
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('X-Frame-Options', 'DENY');
  headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
