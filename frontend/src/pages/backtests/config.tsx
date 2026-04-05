import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createBalance } from "@/lib/api/balances";
import { backtestCreateFormSchema, type BacktestCreateFormValues } from "@/components/shared/form-schemas";
import { useCreateBacktest } from "@/hooks/use-backtests";
import { useCreatePortfolio, usePortfolios } from "@/hooks/use-portfolios";
import { useTemplates } from "@/hooks/use-templates";
import type { PortfolioRead } from "@/lib/types/portfolio";

type BenchmarkOption = { label: string; symbol: string };

const benchmarkOptions: BenchmarkOption[] = [
  { label: "S&P 500", symbol: "^GSPC" },
  { label: "NASDAQ", symbol: "^IXIC" },
  { label: "Dow Jones", symbol: "^DJI" },
];

const initialValues: BacktestCreateFormValues = {
  name: "",
  portfolioMode: "existing",
  portfolioId: "",
  newPortfolioName: "",
  newPortfolioSlug: "",
  newPortfolioCurrency: "USD",
  newPortfolioInitialCash: "",
  createTemplate: false,
  templateId: "",
  templateName: "",
  frequency: "DAILY",
  startDate: "",
  endDate: "",
  priceMode: "CLOSING_PRICE",
  commissionMode: "ZERO",
  commissionValue: "0",
  webhookUrl: "",
  webhookTimeout: "600",
  benchmarkSymbols: [],
};

export function BacktestConfigPage() {
  const navigate = useNavigate();
  const portfoliosQuery = usePortfolios();
  const templatesQuery = useTemplates();
  const createBacktestMutation = useCreateBacktest();
  const createPortfolioMutation = useCreatePortfolio();
  const [values, setValues] = useState<BacktestCreateFormValues>(initialValues);
  const [messages, setMessages] = useState<string[]>([]);

  const validationMessages = useMemo(
    () => buildValidationMessages(values, portfoliosQuery.data ?? []),
    [portfoliosQuery.data, values],
  );

  const updateValue = <Key extends keyof BacktestCreateFormValues>(
    key: Key,
    value: BacktestCreateFormValues[Key],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const handleBenchmarkToggle = (symbol: string) => {
    setValues((current) => ({
      ...current,
      benchmarkSymbols: current.benchmarkSymbols.includes(symbol)
        ? current.benchmarkSymbols.filter((item) => item !== symbol)
        : [...current.benchmarkSymbols, symbol],
    }));
  };

  const handleSubmit = async () => {
    const parsed = backtestCreateFormSchema.safeParse(values);
    const nextMessages = validationMessages.length > 0
      ? validationMessages
      : parsed.success
        ? []
        : parsed.error.issues.map((issue) => issue.message);
    setMessages(nextMessages);
    if (!parsed.success || nextMessages.length > 0) {
      return;
    }

    try {
      let portfolioId = Number(values.portfolioId);

      if (values.portfolioMode === "new") {
        const portfolio = await createPortfolioMutation.mutateAsync({
          name: values.newPortfolioName,
          slug: values.newPortfolioSlug,
          description: null,
          baseCurrency: values.newPortfolioCurrency,
        });
        await createBalance(portfolio.id, {
          label: "Initial Cash",
          amount: values.newPortfolioInitialCash,
          operationType: "DEPOSIT",
        });
        portfolioId = portfolio.id;
      }

      const created = await createBacktestMutation.mutateAsync({
        name: values.name,
        portfolioId,
        templateId: values.createTemplate ? null : Number(values.templateId),
        createTemplate: values.createTemplate,
        templateName: values.createTemplate && values.templateName ? values.templateName : null,
        frequency: values.frequency,
        startDate: values.startDate,
        endDate: values.endDate,
        webhookUrl: values.webhookUrl,
        webhookTimeout: Number(values.webhookTimeout),
        priceMode: values.priceMode,
        commissionMode: values.commissionMode,
        commissionValue: values.commissionValue,
        benchmarkSymbols: values.benchmarkSymbols,
      });

      toast.success(`Backtest "${created.name}" launched`);
      navigate(`/backtests/${created.id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to launch backtest");
    }
  };

  return (
    <div className="max-w-4xl space-y-4 p-4">
      <div className="space-y-0.5">
        <h1 className="text-xl font-semibold tracking-tight">New Backtest</h1>
        <p className="text-xs text-muted-foreground">
          Configure a historical portfolio simulation.
        </p>
      </div>

      <Card>
        <CardContent className="space-y-6 p-4">
          <section className="space-y-2">
            <Label htmlFor="backtest-name">Backtest Name</Label>
            <Input
              id="backtest-name"
              aria-label="Backtest Name"
              value={values.name}
              onChange={(event) => updateValue("name", event.target.value)}
            />
          </section>

          <section className="space-y-3">
            <p className="text-sm font-medium">Portfolio</p>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input
                  checked={values.portfolioMode === "existing"}
                  name="portfolioMode"
                  onChange={() => updateValue("portfolioMode", "existing")}
                  type="radio"
                />
                <span>Use existing</span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  checked={values.portfolioMode === "new"}
                  name="portfolioMode"
                  onChange={() => updateValue("portfolioMode", "new")}
                  type="radio"
                />
                <span>Create new</span>
              </label>
            </div>
            {values.portfolioMode === "existing" ? (
              <div className="space-y-2">
                <Label htmlFor="portfolio-id">Portfolio</Label>
                <select
                  id="portfolio-id"
                  aria-label="Portfolio"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                  value={values.portfolioId}
                  onChange={(event) => updateValue("portfolioId", event.target.value)}
                >
                  <option value="">Select portfolio</option>
                  {(portfoliosQuery.data ?? []).map((portfolio) => (
                    <option key={portfolio.id} value={String(portfolio.id)}>
                      {portfolio.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="new-portfolio-name">Name</Label>
                  <Input
                    id="new-portfolio-name"
                    aria-label="Name"
                    value={values.newPortfolioName}
                    onChange={(event) => updateValue("newPortfolioName", event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-portfolio-slug">Slug</Label>
                  <Input
                    id="new-portfolio-slug"
                    aria-label="Slug"
                    value={values.newPortfolioSlug}
                    onChange={(event) => updateValue("newPortfolioSlug", event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-portfolio-currency">Base Currency</Label>
                  <Input
                    id="new-portfolio-currency"
                    aria-label="Base Currency"
                    value={values.newPortfolioCurrency}
                    onChange={(event) => updateValue("newPortfolioCurrency", event.target.value.toUpperCase())}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-portfolio-initial-cash">Initial Cash</Label>
                  <Input
                    id="new-portfolio-initial-cash"
                    aria-label="Initial Cash"
                    value={values.newPortfolioInitialCash}
                    onChange={(event) => updateValue("newPortfolioInitialCash", event.target.value)}
                  />
                </div>
              </div>
            )}
          </section>

          <section className="space-y-3">
            <p className="text-sm font-medium">Analysis Template</p>
            <label className="flex items-center gap-2 text-sm">
              <input
                aria-label="Create default template"
                checked={values.createTemplate}
                onChange={(event) => updateValue("createTemplate", event.target.checked)}
                type="checkbox"
              />
              <span>Create default template</span>
            </label>
            {!values.createTemplate ? (
              <div className="space-y-2">
                <Label htmlFor="template-id">Template</Label>
                <select
                  id="template-id"
                  aria-label="Template"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                  value={values.templateId}
                  onChange={(event) => updateValue("templateId", event.target.value)}
                >
                  <option value="">Select template</option>
                  {(templatesQuery.data ?? []).map((template) => (
                    <option key={template.id} value={String(template.id)}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="template-name">Template Name</Label>
                <Input
                  id="template-name"
                  aria-label="Template Name"
                  value={values.templateName}
                  onChange={(event) => updateValue("templateName", event.target.value)}
                />
              </div>
            )}
          </section>

          <section className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="frequency">Frequency</Label>
              <select
                id="frequency"
                aria-label="Frequency"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={values.frequency}
                onChange={(event) =>
                  updateValue("frequency", event.target.value as BacktestCreateFormValues["frequency"])
                }
              >
                <option value="DAILY">Daily</option>
                <option value="WEEKLY">Weekly</option>
                <option value="MONTHLY">Monthly</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="price-mode">Price Mode</Label>
              <select
                id="price-mode"
                aria-label="Price Mode"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={values.priceMode}
                onChange={(event) =>
                  updateValue("priceMode", event.target.value as BacktestCreateFormValues["priceMode"])
                }
              >
                <option value="CLOSING_PRICE">Closing Price</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="start-date">Start Date</Label>
              <Input
                id="start-date"
                aria-label="Start Date"
                type="date"
                value={values.startDate}
                onChange={(event) => updateValue("startDate", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="end-date">End Date</Label>
              <Input
                id="end-date"
                aria-label="End Date"
                type="date"
                value={values.endDate}
                onChange={(event) => updateValue("endDate", event.target.value)}
              />
            </div>
          </section>

          <section className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="commission-mode">Commission Mode</Label>
              <select
                id="commission-mode"
                aria-label="Commission Mode"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={values.commissionMode}
                onChange={(event) =>
                  updateValue(
                    "commissionMode",
                    event.target.value as BacktestCreateFormValues["commissionMode"],
                  )
                }
              >
                <option value="ZERO">Zero</option>
                <option value="FIXED">Fixed</option>
                <option value="PERCENTAGE">Percentage</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="commission-value">Commission Value</Label>
              <Input
                id="commission-value"
                aria-label="Commission Value"
                value={values.commissionValue}
                onChange={(event) => updateValue("commissionValue", event.target.value)}
              />
            </div>
          </section>

          <div className="space-y-4">
            <h3 className="text-sm font-medium">External Client Configuration</h3>
            <div className="space-y-2">
              <Label htmlFor="webhook-url">Client Endpoint URL</Label>
              <Input
                id="webhook-url"
                placeholder="http://localhost:5678/client-endpoint/backtest"
                value={values.webhookUrl}
                onChange={(event) => updateValue("webhookUrl", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="webhook-timeout">Client Callback Timeout (seconds)</Label>
              <Input
                id="webhook-timeout"
                type="number"
                min="30"
                max="3600"
                placeholder="600"
                value={values.webhookTimeout}
                onChange={(event) => updateValue("webhookTimeout", event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Ledger waits this long for the external client to finish each cycle and call back (30-3600
                seconds)
              </p>
            </div>
          </div>

          <section className="space-y-2">
            <p className="text-sm font-medium">Benchmarks</p>
            <div className="flex flex-wrap gap-4">
              {benchmarkOptions.map((option) => (
                <label key={option.symbol} className="flex items-center gap-2 text-sm">
                  <input
                    aria-label={option.label}
                    checked={values.benchmarkSymbols.includes(option.symbol)}
                    onChange={() => handleBenchmarkToggle(option.symbol)}
                    type="checkbox"
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="space-y-2 rounded-md border border-dashed p-3">
            <p className="text-sm font-medium">Validation Summary</p>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {(messages.length > 0 ? messages : validationMessages).map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </section>

          <div className="flex justify-end">
            <Button
              onClick={() => void handleSubmit()}
              disabled={createBacktestMutation.isPending || createPortfolioMutation.isPending}
            >
              Launch Backtest
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function buildValidationMessages(values: BacktestCreateFormValues, portfolios: PortfolioRead[]) {
  const messages: string[] = [];

  if (!values.name.trim()) {
    messages.push("Enter a backtest name");
  }
  if (values.portfolioMode === "existing" && !values.portfolioId.trim()) {
    messages.push("Select an existing portfolio");
  }
  if (values.portfolioMode === "existing" && values.portfolioId.trim()) {
    const selectedPortfolio = portfolios.find(
      (portfolio) => String(portfolio.id) === values.portfolioId,
    );
    if (
      selectedPortfolio &&
      selectedPortfolio.balanceCount === 0 &&
      selectedPortfolio.positionCount === 0
    ) {
      messages.push("Selected portfolio must have at least one balance or position");
    }
  }
  if (values.portfolioMode === "new") {
    if (!values.newPortfolioName.trim()) messages.push("Enter a portfolio name");
    if (!values.newPortfolioSlug.trim()) messages.push("Enter a portfolio slug");
    if (!values.newPortfolioInitialCash.trim()) messages.push("Enter an initial cash amount");
  }
  if (!values.createTemplate && !values.templateId.trim()) {
    messages.push("Select a template or create a default one");
  }
  if (!values.startDate || !values.endDate) {
    messages.push("Choose a complete date range");
  }
  if (!values.webhookUrl.trim()) {
    messages.push("Enter a client endpoint URL");
  }
  if (!values.webhookTimeout.trim()) {
    messages.push("Enter a client callback timeout");
  }
  if (values.benchmarkSymbols.length === 0) {
    messages.push("Select at least one benchmark");
  }
  return messages;
}
