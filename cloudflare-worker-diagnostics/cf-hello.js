export default {
  fetch(request) {
    console.log('HELLO_DIAG_HIT', { path: new URL(request.url).pathname, colo: request.cf?.colo || 'unknown' });
    return new Response('hello cf-diag-20261110\n', {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-Diag-Build': 'cf-diag-20261110'
      }
    });
  }
};
