import { ExternalLink as ExternalIcon } from "lucide-react";
import { safeExternalUrl } from "@/lib/validation";
import { cn } from "@/lib/utils";

/** External source link. Non-http(s) values are rendered as inert text, never as a link. */
export function ExternalLink({
  href,
  children,
  className,
}: {
  href: string | null | undefined;
  children?: React.ReactNode;
  className?: string;
}) {
  const safe = safeExternalUrl(href);
  if (!safe) return <span className={cn("break-all text-text-muted", className)}>{children ?? href ?? "—"}</span>;
  return (
    <a
      href={safe}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={cn("inline-flex max-w-full items-center gap-1 break-all text-forest-700 hover:underline", className)}
    >
      <span className="min-w-0 break-all">{children ?? safe}</span>
      <ExternalIcon aria-hidden className="size-3.5 shrink-0" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}
