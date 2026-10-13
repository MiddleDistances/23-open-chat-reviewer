import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SourceRootEditor, { type SourceRootStatus } from "./SourceRootEditor";

afterEach(() => cleanup());

const roots: SourceRootStatus[] = [
  { provider: "codex", path: "/root/.codex", exists: true, readable: true },
  { provider: "claude", path: "/home/reviewer/.claude", exists: false, readable: false, issue: "Folder not found" },
  { provider: "git", path: "/home/reviewer/Projects", exists: true, readable: true },
];

describe("SourceRootEditor", () => {
  it("adds and removes a second Codex folder", () => {
    render(<SourceRootEditor roots={roots} onSave={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Source folders" })).toBeInTheDocument();
    expect(screen.getByText("3 configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit folders" })).toBeInTheDocument();
    expect(screen.queryByText(/Paths apply only to this computer/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit folders" }));

    expect(screen.getByRole("button", { name: "Hide folders" })).toBeInTheDocument();
    expect(screen.getByText(/Paths apply only to this computer/i)).toHaveTextContent(/without deleting archived data/i);
    expect(screen.getAllByText("Ready")).toHaveLength(2);
    expect(screen.getByText(/Missing · Folder not found/)).toBeInTheDocument();
    expect(screen.getAllByRole("textbox", { name: /Codex folder/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Add Codex folder" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Claude folder" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Gemini folder" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Git folder" })).toBeInTheDocument();

    fireEvent.click(document.getElementById("source-root-add-codex")!);
    expect(screen.getAllByRole("textbox", { name: /Codex folder/ })).toHaveLength(2);
    expect(screen.getByText("3 configured")).toBeInTheDocument();
    fireEvent.change(screen.getAllByRole("textbox", { name: /Codex folder/ })[1], {
      target: { value: "/tmp/another-codex" },
    });
    expect(screen.getByText("4 configured")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove Codex folder 2" }));
    expect(screen.getAllByRole("textbox", { name: /Codex folder/ })).toHaveLength(1);
    expect(screen.getByText("3 configured")).toBeInTheDocument();
  });

  it("trims, deduplicates, and saves the complete flat root list", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<SourceRootEditor roots={roots} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit folders" }));

    const codexAdd = document.getElementById("source-root-add-codex");
    expect(codexAdd).toBeInTheDocument();
    fireEvent.click(codexAdd!);
    const codexInputs = screen.getAllByRole("textbox", { name: /Codex folder/ });
    fireEvent.change(codexInputs[1], { target: { value: "  /home/reviewer/.codex  " } });
    fireEvent.change(screen.getByRole("textbox", { name: "Claude folder 1" }), { target: { value: "  /home/reviewer/.claude  " } });
    fireEvent.submit(document.getElementById("source-root-editor-form")!);

    await waitFor(() => expect(onSave).toHaveBeenCalledWith([
      { provider: "codex", path: "/root/.codex" },
      { provider: "codex", path: "/home/reviewer/.codex" },
      { provider: "claude", path: "/home/reviewer/.claude" },
      { provider: "git", path: "/home/reviewer/Projects" },
    ]));
    expect(document.querySelector(".source-root-feedback")).toHaveTextContent(/next sync will use these paths/i);
    expect(screen.getByRole("button", { name: "Save folders" })).toBeInTheDocument();
  });

  it("disables editing when saving is unavailable", () => {
    render(
      <SourceRootEditor
        roots={roots}
        actionsEnabled={false}
        actionsMessage="Open this page on the machine that owns the folders."
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Edit folders" }));

    expect(screen.getByText("Open this page on the machine that owns the folders.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save folders" })).toBeDisabled();
    for (const input of screen.getAllByRole("textbox")) expect(input).toBeDisabled();
    for (const button of screen.getAllByRole("button", { name: /Add (Codex|Claude|Gemini|Git) folder/ })) {
      expect(button).toBeDisabled();
    }
    for (const button of screen.getAllByRole("button", { name: /Remove (Codex|Claude|Git|Gemini) folder/ })) {
      expect(button).toBeDisabled();
    }
  });

  it("gives every rendered button a stable id and action id", () => {
    render(<SourceRootEditor roots={roots} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit folders" }));

    for (const button of screen.getAllByRole("button")) {
      expect(button, button.textContent ?? "unnamed button").toHaveAttribute("id");
      expect(button, button.textContent ?? "unnamed button").toHaveAttribute("data-action-id");
    }
  });
});
