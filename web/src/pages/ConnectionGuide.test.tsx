import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ConnectionOverview,
  WriterSetupGuide,
  type SetupConnection,
} from "./ConnectionGuide";

afterEach(() => cleanup());

const localOnly: SetupConnection = {
  centralMachine: { id: "central", name: "Central host", hostname: "central" },
  web: { url: "http://central.example.ts.net:8766", host: "0.0.0.0", port: 8766 },
  database: {
    localEndpoint: "127.0.0.1:54329",
    writerEndpoint: null,
    remoteReady: false,
  },
  tailscale: {
    connected: true,
    ipv4: "100.64.0.1",
    dnsName: "central.example.ts.net",
  },
  networkScan: false,
  warnings: ["The database is local-only."],
};

describe("multi-machine connection guide", () => {
  it("draws the architecture and does not invent a remote database address", () => {
    render(<ConnectionOverview connection={localOnly} machineCount={1} />);

    expect(screen.getAllByRole("img", { name: /multi-machine architecture/i })).toHaveLength(2);
    expect(screen.getByText("http://central.example.ts.net:8766")).toBeInTheDocument();
    expect(screen.getByText("127.0.0.1:54329")).toBeInTheDocument();
    expect(screen.getByText(/writers cannot connect yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /copy/i })).toBeInTheDocument();
    expect(document.querySelector("#setup-copy-database-address")).not.toBeInTheDocument();
  });

  it("builds one platform-specific writer command without putting credentials in it", () => {
    render(
      <WriterSetupGuide
        connection={localOnly}
        checking={false}
        guideAvailable
        refreshAvailable
        onOpenGuide={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/name this computer/i), {
      target: { value: "Michaels MacBook" },
    });
    fireEvent.click(screen.getByRole("button", { name: "macOS" }));

    expect(screen.getByText(/brew install flock/i)).toBeInTheDocument();
    expect(screen.getByText(/writer install ~\/Downloads\/michaels-macbook.env/i)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/postgresql is currently local-only/i);
    expect(document.body.textContent).not.toMatch(/postgres(?:ql)?:\/\//i);
  });
});
