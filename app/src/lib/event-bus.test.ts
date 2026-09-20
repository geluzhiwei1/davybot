import { describe, it, expect } from "vitest";
import { emit, on } from "./event-bus";

describe("event-bus", () => {
  it("delivers events to subscribers", () => {
    const received: Array<Record<string, unknown>> = [];
    const unsub = on("test:event", (detail) => {
      received.push(detail);
    });

    emit("test:event", { foo: "bar" });
    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({ foo: "bar" });

    unsub();
  });

  it("unsubscribes correctly", () => {
    const received: unknown[] = [];
    const unsub = on("test:unsub", (detail) => {
      received.push(detail);
    });

    emit("test:unsub", { a: 1 });
    expect(received).toHaveLength(1);

    unsub();
    emit("test:unsub", { a: 2 });
    expect(received).toHaveLength(1); // still 1, not 2
  });

  it("supports multiple subscribers for same event", () => {
    const received1: unknown[] = [];
    const received2: unknown[] = [];
    const unsub1 = on("test:multi", (d) => received1.push(d));
    const unsub2 = on("test:multi", (d) => received2.push(d));

    emit("test:multi", { x: 1 });
    expect(received1).toHaveLength(1);
    expect(received2).toHaveLength(1);

    unsub1();
    unsub2();
  });

  it("does not receive events of different types", () => {
    const received: unknown[] = [];
    const unsub = on("test:type_a", (d) => received.push(d));

    emit("test:type_b", { x: 1 });
    expect(received).toHaveLength(0);

    emit("test:type_a", { x: 2 });
    expect(received).toHaveLength(1);

    unsub();
  });

  it("handles events without payload", () => {
    const received: unknown[] = [];
    const unsub = on("test:nopayload", (d) => received.push(d));

    emit("test:nopayload");
    expect(received).toHaveLength(1);
    // CustomEvent with undefined detail becomes null
    expect(received[0]).toBeNull();

    unsub();
  });
});
