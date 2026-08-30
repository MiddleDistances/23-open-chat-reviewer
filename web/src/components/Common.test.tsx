import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Highlight, ProviderOptions, formatBytes, formatHours, projectName } from "./Common";

describe("corpus presentation helpers", () => {
  it("renders FTS emphasis as safe React nodes", () => {
    render(
      <p>
        <Highlight html="before <mark>failure</mark> after" />
      </p>,
    );
    expect(screen.getByText("failure").tagName).toBe("MARK");
    expect(screen.getByText(/before/)).toBeInTheDocument();
  });

  it("formats source paths and byte counts compactly", () => {
    expect(projectName("/work/projects/open-chat-reviewer")).toBe("open-chat-reviewer");
    expect(formatBytes(10 * 1024 * 1024)).toBe("10.0 MiB");
    expect(formatHours(95.5 * 24 * 3600)).toBe("2,292h");
    expect(formatHours(90 * 60)).toBe("1.5h");
  });

  it("offers every supported conversation provider", () => {
    render(<select aria-label="Provider"><ProviderOptions /></select>);
    expect(screen.getByRole("option", { name: "Codex" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Claude" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Gemini" })).toBeInTheDocument();
  });
});
