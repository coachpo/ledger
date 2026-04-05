import { z } from "zod";

import type { TradingSide } from "@/lib/types/trading";

const tradingSides = ["BUY", "SELL", "DIVIDEND", "SPLIT"] as const satisfies readonly TradingSide[];
const balanceOperationTypes = ["DEPOSIT", "WITHDRAWAL"] as const;

const requiredText = (label: string) =>
  z.string().trim().min(1, `${label} is required`);

const numericText = (label: string) =>
  requiredText(label).refine((value) => Number.isFinite(Number(value)), {
    message: `${label} must be a valid number`,
  });

const optionalText = z.string();
const portfolioSlugText = requiredText("Slug").regex(
  /^[a-z][a-z0-9_]*$/,
  "Slug must start with a letter and use only lowercase letters, numbers, and underscores",
);
const symbolText = requiredText("Symbol").transform((value) => value.toUpperCase());
const validDateTimeText = requiredText("Executed at").refine(
  (value) => !Number.isNaN(new Date(value).getTime()),
  "Executed at must be a valid date",
);

export const balanceFormSchema = z.object({
  amount: numericText("Amount"),
  label: requiredText("Label"),
  operationType: z.enum(balanceOperationTypes),
});

export const portfolioCreateFormSchema = z.object({
  baseCurrency: z.string().trim().length(3, "Base currency must be a 3-letter code"),
  description: optionalText,
  name: requiredText("Name"),
  slug: portfolioSlugText,
});

export const portfolioUpdateFormSchema = z.object({
  description: optionalText,
  name: requiredText("Name"),
});

export const positionCreateFormSchema = z.object({
  averageCost: numericText("Average cost"),
  name: optionalText,
  quantity: numericText("Quantity"),
  symbol: symbolText,
});

export const positionUpdateFormSchema = z.object({
  averageCost: numericText("Average cost"),
  name: optionalText,
  quantity: numericText("Quantity"),
});

export const tradingOperationFormSchema = z
  .object({
    balanceId: optionalText,
    commission: optionalText,
    dividendAmount: optionalText,
    executedAt: validDateTimeText,
    price: optionalText,
    quantity: optionalText,
    side: z.enum(tradingSides),
    splitRatio: optionalText,
    symbol: symbolText,
  })
  .superRefine((value, ctx) => {
    if (value.side === "BUY" || value.side === "SELL") {
      if (!value.balanceId.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Balance is required",
          path: ["balanceId"],
        });
      }

      if (!value.quantity.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Quantity is required",
          path: ["quantity"],
        });
      } else if (!Number.isFinite(Number(value.quantity))) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Quantity must be a valid number",
          path: ["quantity"],
        });
      }

      if (!value.price.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Price is required",
          path: ["price"],
        });
      } else if (!Number.isFinite(Number(value.price))) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Price must be a valid number",
          path: ["price"],
        });
      }

      return;
    }

    if (value.side === "DIVIDEND") {
      if (!value.balanceId.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Balance is required",
          path: ["balanceId"],
        });
      }

      if (!value.dividendAmount.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Dividend amount is required",
          path: ["dividendAmount"],
        });
      } else if (!Number.isFinite(Number(value.dividendAmount))) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Dividend amount must be a valid number",
          path: ["dividendAmount"],
        });
      }

      return;
    }

    if (!value.splitRatio.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Split ratio is required",
        path: ["splitRatio"],
      });
    }
  });

export const backtestCreateFormSchema = z
  .object({
    name: requiredText("Backtest name"),
    portfolioMode: z.enum(["existing", "new"]),
    portfolioId: z.string(),
    newPortfolioName: optionalText,
    newPortfolioSlug: optionalText,
    newPortfolioCurrency: z.string().trim().length(3, "Base currency must be a 3-letter code"),
    newPortfolioInitialCash: optionalText,
    createTemplate: z.boolean(),
    templateId: z.string(),
    templateName: optionalText,
    frequency: z.enum(["DAILY", "WEEKLY", "MONTHLY"]),
    startDate: requiredText("Start date"),
    endDate: requiredText("End date"),
    priceMode: z.enum(["CLOSING_PRICE"]),
    commissionMode: z.enum(["ZERO", "FIXED", "PERCENTAGE"]),
    commissionValue: numericText("Commission value"),
    webhookUrl: requiredText("Client endpoint URL"),
    webhookTimeout: numericText("Client callback timeout"),
    benchmarkSymbols: z.array(z.string()).min(1, "Select at least one benchmark"),
  })
  .superRefine((value, ctx) => {
    if (value.portfolioMode === "existing" && !value.portfolioId.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Select a portfolio",
        path: ["portfolioId"],
      });
    }

    if (value.portfolioMode === "new") {
      if (!value.newPortfolioName.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Portfolio name is required",
          path: ["newPortfolioName"],
        });
      }
      if (!value.newPortfolioSlug.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Portfolio slug is required",
          path: ["newPortfolioSlug"],
        });
      }
      if (!value.newPortfolioInitialCash.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Initial cash is required",
          path: ["newPortfolioInitialCash"],
        });
      }
    }

    if (!value.createTemplate && !value.templateId.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Select a template or create a default one",
        path: ["templateId"],
      });
    }


  });

export type BalanceFormValues = z.infer<typeof balanceFormSchema>;
export type BacktestCreateFormValues = z.infer<typeof backtestCreateFormSchema>;
export type PortfolioCreateFormValues = z.infer<typeof portfolioCreateFormSchema>;
export type PortfolioUpdateFormValues = z.infer<typeof portfolioUpdateFormSchema>;
export type PositionCreateFormValues = z.infer<typeof positionCreateFormSchema>;
export type PositionUpdateFormValues = z.infer<typeof positionUpdateFormSchema>;
export type TradingOperationFormValues = z.infer<typeof tradingOperationFormSchema>;
