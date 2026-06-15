import { cva } from "class-variance-authority";

export const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium shadow-none outline-none transition-[background-color,border-color,color,box-shadow,opacity] duration-[var(--ui-motion-duration-base)] ease-[var(--ui-motion-ease-standard)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 focus-visible:border-ring focus-visible:ring-0 focus-visible:[box-shadow:var(--ui-focus-shadow)] aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-ui-xs hover:bg-primary/90 active:bg-primary/85",
        destructive:
          "bg-destructive text-white shadow-ui-xs hover:bg-destructive/90 active:bg-destructive/85 focus-visible:ring-destructive/20 dark:bg-destructive/70",
        outline:
          "border border-border/80 bg-ui-surface-elevated/80 text-foreground shadow-ui-xs hover:border-border hover:bg-accent/70 hover:text-accent-foreground active:bg-accent dark:bg-input/35 dark:hover:bg-input/55",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 active:bg-secondary/70",
        ghost:
          "text-foreground/90 hover:bg-accent/70 hover:text-accent-foreground active:bg-accent dark:hover:bg-accent/50",
        link: "h-auto rounded-sm px-0 text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-[var(--ui-size-control-md)] px-4 py-2 has-[>svg]:px-3",
        sm: "h-[var(--ui-size-control-sm)] gap-1.5 rounded-md px-3 text-xs has-[>svg]:px-2.5",
        lg: "h-[var(--ui-size-control-lg)] rounded-lg px-5 has-[>svg]:px-4",
        icon: "size-[var(--ui-size-control-md)] rounded-md",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);
