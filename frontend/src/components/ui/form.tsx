import { forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

const control =
  "h-10 w-full rounded-md border border-line-strong bg-surface px-3 text-sm text-text placeholder:text-text-subtle " +
  "shadow-card transition-colors hover:border-ink-300 focus-visible:border-forest-500 focus-visible:outline-2 " +
  "focus-visible:outline-offset-0 focus-visible:outline-forest-500/40 aria-[invalid=true]:border-danger disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref,
) {
  return <input ref={ref} className={cn(control, className)} {...props} />;
});

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...props },
  ref,
) {
  return (
    <select ref={ref} className={cn(control, "cursor-pointer pr-8", className)} {...props}>
      {children}
    </select>
  );
});

/** Accessible label + control + hint/error wiring. */
export function FormField({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: React.ReactNode;
  error?: string | null;
  className?: string;
  children: (ids: { id: string; describedBy: string | undefined; invalid: boolean }) => React.ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={id} className="block text-[13px] font-medium text-text">
        {label}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {error ? (
        <p id={errorId} className="text-[12.5px] text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="text-[12.5px] text-text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** Two-option segmented control rendered as a radio group (keyboard: arrows / tab). */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  className,
  tone = "light",
}: {
  label: string;
  value: T;
  options: { value: T; label: string; description?: string }[];
  onChange: (v: T) => void;
  className?: string;
  tone?: "light" | "dark";
}) {
  const name = useId();
  return (
    <fieldset className={cn("min-w-0", className)}>
      <legend className="sr-only">{label}</legend>
      <div
        className={cn(
          "inline-flex rounded-md p-0.5",
          tone === "dark" ? "bg-white/[0.06] ring-1 ring-white/10" : "bg-black/[0.04] ring-1 ring-line",
        )}
      >
        {options.map((o) => {
          const checked = o.value === value;
          return (
            <label
              key={o.value}
              title={o.description}
              className={cn(
                "relative cursor-pointer rounded-[5px] px-3 py-1.5 text-[13px] font-medium whitespace-nowrap transition-colors select-none",
                "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-forest-500",
                checked
                  ? tone === "dark"
                    ? "bg-white text-ink-900 shadow-card"
                    : "bg-surface text-text shadow-card"
                  : tone === "dark"
                    ? "text-ink-200 hover:text-white"
                    : "text-text-muted hover:text-text",
              )}
            >
              <input
                type="radio"
                name={name}
                value={o.value}
                checked={checked}
                onChange={() => onChange(o.value)}
                className="sr-only"
              />
              {o.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
