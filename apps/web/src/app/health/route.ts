export function GET() {
  return Response.json({status: "ok", service: "aevyra-web"}, {
    headers: {"Cache-Control": "no-store"},
  });
}
