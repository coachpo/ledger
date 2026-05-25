import { useEffect, useState, type InputHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type SecretInputProps = {
  helperText?: string;
  id: string;
  label: string;
  value: string;
  onValueChange: (value: string) => void;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "label" | "type" | "value" | "onChange">;

export function SecretInput({
  disabled = false,
  helperText,
  id,
  label,
  onValueChange,
  value,
  ...props
}: SecretInputProps) {
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    if (!value) {
      setRevealed(false);
    }
  }, [value]);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id}>{label}</Label>
        <Button
          disabled={disabled || value.length === 0}
          size="sm"
          type="button"
          variant="ghost"
          className="h-auto px-0 text-xs text-muted-foreground"
          onClick={() => setRevealed((current) => !current)}
        >
          {revealed ? <EyeOff data-icon="inline-start" /> : <Eye data-icon="inline-start" />}
          {revealed ? "Hide" : "Reveal"}
        </Button>
      </div>
      <Input
        {...props}
        autoComplete="new-password"
        disabled={disabled}
        id={id}
        spellCheck={false}
        type={revealed ? "text" : "password"}
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
      />
      {helperText ? <p className="text-sm text-muted-foreground">{helperText}</p> : null}
    </div>
  );
}
