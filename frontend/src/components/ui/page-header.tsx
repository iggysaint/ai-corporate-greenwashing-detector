import { cn } from "@/lib/utils";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 pb-6 md:flex-row md:items-end md:justify-between", className)}>
      <div className="min-w-0">
        {eyebrow ? (
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px] font-medium tracking-wider text-text-subtle uppercase">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="font-serif text-[28px] leading-tight font-semibold tracking-tight text-text md:text-[32px]">
          {title}
        </h1>
        {description ? (
          <p className="mt-2 max-w-3xl text-[14.5px] leading-relaxed text-text-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function SectionHeading({ children, id, className }: { children: React.ReactNode; id?: string; className?: string }) {
  return (
    <h2 id={id} className={cn("mb-3 text-[12px] font-semibold tracking-wider text-text-subtle uppercase", className)}>
      {children}
    </h2>
  );
}
