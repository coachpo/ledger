let markdownFormatterModules:
  | Promise<
      [
        typeof import("prettier/standalone"),
        typeof import("prettier/plugins/markdown"),
      ]
    >
  | undefined;

export async function formatMarkdown(markdown: string): Promise<string> {
  markdownFormatterModules ??= Promise.all([
    import("prettier/standalone"),
    import("prettier/plugins/markdown"),
  ]);

  const [prettier, markdownPlugin] = await markdownFormatterModules;

  return prettier.format(markdown, {
    parser: "markdown",
    plugins: [markdownPlugin],
    proseWrap: "preserve",
  });
}
