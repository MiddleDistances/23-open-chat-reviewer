import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./pages/DashboardPage", () => ({ default: () => <div>Focus route</div> }));

afterEach(() => cleanup());

describe("application navigation", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("opens and closes the navigation menu", async () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Focus route")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Open navigation" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(document.querySelector("main")).toHaveAttribute("aria-hidden", "true");

    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(screen.getByRole("button", { name: "Open navigation" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(document.querySelector("main")).not.toHaveAttribute("aria-hidden");
  });

  it("starts with a simple navigation and reveals specialist tools on request", async () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Focus route")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Home/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Search/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Workload/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Setup/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Chat trace/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Episodes/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show advanced tools" }));

    expect(screen.getByRole("link", { name: /Chat trace/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Episodes/ })).toBeInTheDocument();
    expect(window.localStorage.getItem("open-chat-reviewer.experience-mode")).toBe("advanced");
  });
});
