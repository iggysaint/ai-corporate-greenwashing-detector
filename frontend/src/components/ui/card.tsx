import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-line bg-surface shadow-card", className)} {...props} />;
}

export function CardHeader({
  title,
  description,
  action,
  className,
  as: Heading = "h2",
  id,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  as?: "h2" | "h3";
  id?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4", className)}>
      <div className="min-w-0">
        <Heading id={id} className="text-[15px] font-semibold text-text">
          {title}
        </Heading>
        {description ? <p className="mt-0.5 text-[13px] leading-relaxed text-text-muted">{description}</p> : null}
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </div>
  );
}

export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4", className)} {...props} />;
}

/** Label/value pair used in metadata grids. Renders an explicit "Not available" when value is empty. */
export function Field({
  label,
  value,
  mono,
  className,
}: {
  label: string;
  value: React.ReactNode | null | undefined;
  mono?: boolean;
  className?: string;
}) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-[11px] font-medium tracking-wider text-text-subtle uppercase">{label}</dt>
      <dd
        className={cn(
          "mt-1 text-sm break-words",
          empty ? "text-text-subtle italic" : "text-text",
          mono && !empty && "font-mono text-[13px]",
        )}
      >
        {empty ? "Not available" : value}
      </dd>
    </div>
  );
}
