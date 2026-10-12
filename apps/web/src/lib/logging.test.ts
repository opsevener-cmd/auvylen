import {expect, it, vi} from "vitest";
import {logFailure} from "./logging";

it("logs safe structured failure metadata without exception text", () => {
  const output = vi.spyOn(console, "error").mockImplementation(() => {});
  try {
    logFailure("request_failed", new Error("private-password-and-token"));
    const line = output.mock.calls[0][0];
    expect(JSON.parse(line)).toMatchObject({service: "aevyra-web", level: "ERROR", error_type: "Error"});
    expect(line).not.toContain("private-password");
  } finally {
    output.mockRestore();
  }
});
