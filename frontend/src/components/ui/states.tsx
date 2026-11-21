import { AlertTriangle, Info, Loader2, RotateCcw, SearchX, ShieldAlert } from "lucide-react";
import { describeError, isApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Button } from "./button";

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span role="status" className="inline-flex items-center">
      <Loader2 aria-hidden className={cn("size-4 animate-spin text-forest-600", className)} />
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function LoadingState({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex items-center gap-3 rounded-lg border border-line bg-surface px-5 py-6 text-sm text-text-muted", className)}
    >
      <Loader2 aria-hidden className="size-4 animate-spin text-forest-600" />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded bg-black/[0.06]", className)} />;
}

export function ErrorState({
  error,
  onRetry,
  className,
  compact,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
  compact?: boolean;
}) {
  const { title, message, hint } = describeError(error);
  const status = isApiError(error) && error.status ? error.status : null;
  const code = isApiError(error) ? error.code : null;
  const Icon = isApiError(error) && (error.status === 403 || error.code === "ssrf_security_violation") ? ShieldAlert : AlertTriangle;
  return (
    <div
      role="alert"
      className={cn(
        "rounded-lg border border-danger/25 bg-danger-bg/60",
        compact ? "px-4 py-3" : "px-5 py-4",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-text">
            {title}
            {status ? " " : null}
            {status ? <span className="ml-2 font-mono text-[12px] font-normal text-text-muted">HTTP {status}</span> : null}
            {code ? " " : null}
            {code ? <span className="ml-2 font-mono text-[12px] font-normal text-text-muted">{code}</span> : null}
          </p>
          <p className="mt-1 text-[13px] leading-relaxed break-words text-text-muted">{message}</p>
          {hint ? <p className="mt-1.5 text-[13px] leading-relaxed text-text">{hint}</p> : null}
          {onRetry ? (
            <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
              <RotateCcw aria-hidden />
              Retry
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({
  icon: Icon = SearchX,
  title,
  children,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-lg border border-dashed border-line-strong bg-surface-muted px-6 py-10 text-center",
        className,
      )}
    >
      <span className="flex size-10 items-center justify-center rounded-full bg-black/[0.04]">
        <Icon aria-hidden className="size-5 text-text-subtle" />
      </span>
      <h3 className="mt-3 text-[15px] font-semibold text-text">{title}</h3>
      {children ? <div className="mt-1.5 max-w-md text-[13px] leading-relaxed text-text-muted">{children}</div> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: "info" | "warn";
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const Icon = tone === "warn" ? AlertTriangle : Info;
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-lg border px-4 py-3 text-[13px] leading-relaxed",
        tone === "warn" ? "border-warn/20 bg-warn-bg text-text" : "border-info/15 bg-info-bg text-text",
        className,
      )}
    >
      <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", tone === "warn" ? "text-warn" : "text-info")} />
      <div className="min-w-0">
        {title ? <p className="font-semibold">{title}</p> : null}
        <div className={cn(title && "mt-0.5", "text-text-muted [&_strong]:text-text")}>{children}</div>
      </div>
    </div>
  );
}
