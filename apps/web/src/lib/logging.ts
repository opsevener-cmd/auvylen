export function logFailure(event: string, error: unknown, level: "ERROR" | "WARNING" = "ERROR") {
  // Do not serialize error messages, stack traces, URLs or request payloads.
  const line = JSON.stringify({
    timestamp: new Date().toISOString(), service: "aevyra-web", level, event,
    error_type: error instanceof Error ? error.name : "unknown",
  });
  if (level === "ERROR") console.error(line);
  else console.warn(line);
}
