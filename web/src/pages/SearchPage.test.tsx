import { describe, expect, it } from "vitest";
import { searchDateRange } from "./SearchPage";

describe("search date constraints", () => {
  it("turns the default recent range into inclusive dates", () => {
    expect(searchDateRange("30d", new Date(2026, 7, 30))).toEqual({
      dateFrom: "2026-08-01",
      dateTo: "2026-08-30",
    });
  });

  it("leaves all-time and custom ranges unbounded until the user supplies dates", () => {
    expect(searchDateRange("all", new Date(2026, 7, 30))).toEqual({ dateFrom: "", dateTo: "" });
    expect(searchDateRange("custom", new Date(2026, 7, 30))).toEqual({ dateFrom: "", dateTo: "" });
  });
});
