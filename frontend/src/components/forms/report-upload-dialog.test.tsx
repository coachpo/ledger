import type { ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportUploadDialog } from "./report-upload-dialog";

function expectSharedDialogShell(dialog: HTMLElement) {
  const constraintStrip = dialog.querySelector(
    '[data-slot="entity-dialog-constraint-strip"]',
  );
  const body = dialog.querySelector('[data-slot="entity-dialog-body"]');
  const footer = dialog.querySelector('[data-slot="dialog-footer"]');

  expect(constraintStrip).toBeTruthy();
  expect(body).toBeTruthy();
  expect(footer).toBeTruthy();
  expect(
    Array.from(
      dialog.querySelectorAll(
        '[data-slot="entity-dialog-constraint-strip"], [data-slot="entity-dialog-body"], [data-slot="dialog-footer"]',
      ),
    ),
  ).toEqual([constraintStrip, body, footer]);
}

function renderDialog(
  overrides: Partial<ComponentProps<typeof ReportUploadDialog>> = {},
) {
  const props = {
    author: "",
    description: "",
    isPending: false,
    open: true,
    slug: "",
    tags: "",
    uploadFile: null,
    onAuthorChange: vi.fn(),
    onDescriptionChange: vi.fn(),
    onFileChange: vi.fn(),
    onOpenChange: vi.fn(),
    onSlugChange: vi.fn(),
    onTagsChange: vi.fn(),
    onUpload: vi.fn(),
    ...overrides,
  };

  return { ...render(<ReportUploadDialog {...props} />), props };
}

describe("ReportUploadDialog", () => {
  it("renders a parent-controlled markdown upload form", () => {
    const file = new File(["# Report"], "Quarterly Review.md", {
      type: "text/markdown",
    });
    const { props, rerender } = renderDialog();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Upload Report");
    expectSharedDialogShell(dialog);
    expect(dialog).toHaveTextContent("Required markdown");
    expect(dialog).toHaveTextContent("Metadata");
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Markdown File"), {
      target: { files: [file] },
    });
    expect(props.onFileChange).toHaveBeenCalledWith(file);

    rerender(
      <ReportUploadDialog
        {...props}
        slug="quarterly_review"
        uploadFile={file}
      />,
    );
    expect(screen.getByRole("dialog")).toHaveTextContent("Quarterly Review.md");
    expect(screen.getByRole("dialog")).toHaveTextContent("quarterly_review");

    fireEvent.change(screen.getByLabelText("Slug"), {
      target: { value: "custom_slug" },
    });
    fireEvent.change(screen.getByLabelText("Author (optional)"), {
      target: { value: "Research Desk" },
    });
    fireEvent.change(screen.getByLabelText("Description (optional)"), {
      target: { value: "Uploaded markdown report" },
    });
    fireEvent.change(screen.getByLabelText("Tags (optional)"), {
      target: { value: "finance, q1" },
    });

    expect(props.onSlugChange).toHaveBeenCalledWith("custom_slug");
    expect(props.onAuthorChange).toHaveBeenCalledWith("Research Desk");
    expect(props.onDescriptionChange).toHaveBeenCalledWith(
      "Uploaded markdown report",
    );
    expect(props.onTagsChange).toHaveBeenCalledWith("finance, q1");

    fireEvent.submit(
      screen.getByRole("button", { name: "Upload" }).closest("form")!,
    );
    expect(props.onUpload).toHaveBeenCalledTimes(1);
  });

  it("lets the parent close or lock the dialog", () => {
    const { props } = renderDialog({
      isPending: true,
      slug: "daily_report",
      uploadFile: new File(["# Report"], "daily.md"),
    });

    expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
    expect(screen.getByLabelText("Markdown File")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onOpenChange).not.toHaveBeenCalled();
  });
});
