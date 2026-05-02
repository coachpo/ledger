import { type ReactNode, useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SchemaIRNode } from "@/lib/platform-authoring/schema/types";
import {
  createObjectValueEntry,
  createStringValueEntry,
  createValueEntryObjectField,
} from "@/lib/platform-authoring/values/factories";
import type { ValueEntry } from "@/lib/platform-authoring/values/types";

import { SchemaForm } from "./schema-form";

Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", {
  configurable: true,
  value: () => false,
});

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});

type StatefulSchemaFormProps = {
  children?: ReactNode;
  onChange?: (nextValue: ValueEntry) => void;
  schema: SchemaIRNode;
  value?: ValueEntry | null;
};

function StatefulSchemaForm({ children, onChange, schema, value }: StatefulSchemaFormProps) {
  const [currentValue, setCurrentValue] = useState<ValueEntry | null | undefined>(value);

  return (
    <>
      <SchemaForm
        label="Run input"
        onChange={(nextValue) => {
          setCurrentValue(nextValue);
          onChange?.(nextValue);
        }}
        schema={schema}
        value={currentValue}
      />
      {children}
    </>
  );
}

function openSelect(label: string) {
  const trigger = screen.getByLabelText(label);
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return trigger;
}

describe("SchemaForm", () => {
  it("uses schema titles for field labels, falls back to property keys, and preserves value-entry payloads", () => {
    const onChange = vi.fn();
    const schema = {
      fields: [
        {
          name: "ticker",
          schema: {
            description: "Use the exchange ticker exactly as the run expects.",
            kind: "string",
            title: "Ticker",
          },
        },
        { name: "strategy", schema: { kind: "string" } },
        {
          name: "dryRun",
          schema: {
            description: "Preview execution without sending orders.",
            kind: "boolean",
            title: "Dry Run",
          },
        },
        {
          name: "kind",
          schema: {
            description: "The manifest fixes this literal value.",
            kind: "literal",
            title: "Run Kind",
            value: "backtest",
          },
        },
        {
          name: "lots",
          schema: {
            description: "Provide each execution lot in order.",
            items: { kind: "number" },
            kind: "array",
            title: "Lots",
          },
        },
      ],
      kind: "object",
      title: "Run Ticket",
    } satisfies SchemaIRNode;

    render(<StatefulSchemaForm onChange={onChange} schema={schema} />);

    expect(screen.getByText("Run Ticket")).toBeVisible();
    expect(screen.getByLabelText("Ticker")).toBeVisible();
    expect(screen.getByLabelText("strategy")).toBeVisible();
    expect(screen.getByText("Use the exchange ticker exactly as the run expects.")).toBeVisible();
    expect(screen.getByText("Preview execution without sending orders.")).toBeVisible();
    expect(screen.getByText("The manifest fixes this literal value.")).toBeVisible();
    expect(screen.getByText("Provide each execution lot in order.")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "AAPL" } });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        fields: expect.arrayContaining([
          expect.objectContaining({
            key: "ticker",
            pathTokens: ["ticker"],
            value: expect.objectContaining({
              kind: "string",
              pathTokens: ["ticker"],
              value: "AAPL",
            }),
          }),
        ]),
        kind: "object",
        pathTokens: [],
      }),
    );
  });

  it("shows optional field titles and descriptions before and after adding them", () => {
    const onChange = vi.fn();
    const schema = {
      fields: [
        {
          name: "limit",
          required: false,
          schema: {
            description: "Optional cap applied only when the run needs a guardrail.",
            kind: "number",
            title: "Risk Limit",
          },
        },
      ],
      kind: "object",
    } satisfies SchemaIRNode;

    render(<StatefulSchemaForm onChange={onChange} schema={schema} />);

    expect(screen.getByText("Risk Limit")).toBeVisible();
    expect(screen.getByText("Optional cap applied only when the run needs a guardrail.")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /add field/i }));

    expect(screen.getByRole("button", { name: /remove optional field/i })).toBeVisible();
    expect(screen.getByLabelText("Risk Limit")).toHaveValue(0);
    expect(screen.getAllByText("Optional cap applied only when the run needs a guardrail.")).toHaveLength(1);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        fields: [
          expect.objectContaining({
            key: "limit",
            pathTokens: ["limit"],
            value: expect.objectContaining({ kind: "number", pathTokens: ["limit"], value: 0 }),
          }),
        ],
      }),
    );
  });

  it("uses enum descriptions while keeping the allowed option list constrained", () => {
    const schema = {
      fields: [
        {
          name: "mode",
          schema: {
            description: "Choose how aggressively this run should execute.",
            kind: "enum",
            title: "Execution Mode",
            values: ["fast", "slow"],
          },
        },
      ],
      kind: "object",
    } satisfies SchemaIRNode;

    render(<StatefulSchemaForm schema={schema} />);

    const trigger = openSelect("Execution Mode enum value");
    expect(trigger).toHaveTextContent("fast");
    expect(screen.getByText("Choose how aggressively this run should execute.")).toBeVisible();
    expect(screen.getByRole("option", { name: "fast" })).toBeVisible();
    expect(screen.getByRole("option", { name: "slow" })).toBeVisible();
    expect(screen.queryByRole("option", { name: "balanced" })).not.toBeInTheDocument();
  });

  it("uses discriminated union branch titles in the selector and branch descriptions in the selected editor", () => {
    const schema = {
      discriminator: "type",
      kind: "discriminated_union",
      title: "Order Input",
      variants: [
        {
          description: "Configure stock order branch.",
          fields: [
            { name: "type", schema: { kind: "literal", value: "stock" } },
            { name: "symbol", schema: { kind: "string", title: "Symbol" } },
          ],
          kind: "object",
          title: "Equity Order",
        },
        {
          fields: [
            { name: "type", schema: { kind: "literal", value: "cash" } },
            { name: "amount", schema: { kind: "number" } },
          ],
          kind: "object",
          title: "Cash Order",
        },
      ],
    } satisfies SchemaIRNode;

    render(<StatefulSchemaForm schema={schema} />);

    const trigger = openSelect("Order Input variant");
    expect(trigger).toHaveTextContent("Equity Order");
    expect(screen.getByRole("option", { name: "Equity Order" })).toBeVisible();
    expect(screen.getByRole("option", { name: "Cash Order" })).toBeVisible();
    expect(screen.getByText("Configure stock order branch.")).toBeVisible();
  });

  it("keeps selected union branches without descriptions on the existing object fallback copy", () => {
    const schema = {
      discriminator: "type",
      kind: "discriminated_union",
      title: "Order Input",
      variants: [
        {
          fields: [{ name: "type", schema: { kind: "literal", value: "stock" } }],
          kind: "object",
          title: "Equity Order",
        },
        {
          fields: [
            { name: "type", schema: { kind: "literal", value: "cash" } },
            { name: "amount", schema: { kind: "number" } },
          ],
          kind: "object",
          title: "Cash Order",
        },
      ],
    } satisfies SchemaIRNode;
    const cashValue = createObjectValueEntry(
      [
        createValueEntryObjectField(
          "type",
          createStringValueEntry("cash", ["type"]),
          ["type"],
        ),
      ],
      [],
    );

    render(<StatefulSchemaForm schema={schema} value={cashValue} />);

    expect(screen.getByLabelText("Order Input variant")).toHaveTextContent("Cash Order");
    expect(screen.getAllByText("Cash Order").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Capture object fields without dropping the shared value-entry structure.")).toBeVisible();
  });
});
