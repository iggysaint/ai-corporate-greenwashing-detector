"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Menu, X } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { api } from "@/lib/api/endpoints";
import { getApiBaseUrl } from "@/lib/api/client";
import type { MarketId } from "@/lib/api/types";
import { MARKETS } from "@/lib/format";
import { routes, withContext } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { Segmented } from "@/components/ui/form";
import { NAV_ITEMS } from "./nav-items";

function BrandMark() {
  return (
    <span aria-hidden className="flex size-8 items-center justify-center rounded-md bg-forest-600 ring-1 ring-white/10">
      <svg viewBox="0 0 24 24" className="size-[18px] text-white" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M5 19V9M12 19V5M19 19v-7" strokeLinecap="round" />
        <path d="M3.5 19.5h17" strokeLinecap="round" />
      </svg>
    </span>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { activeCompany } = useWorkspace();
  return (
    <nav aria-label="Primary">
      <ul className="space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const href = item.needsCompany && activeCompany ? withContext(item.href, activeCompany) : item.href;
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group flex items-center gap-3 rounded-md px-3 py-2 text-[13.5px] font-medium transition-colors",
                  active ? "bg-white/[0.09] text-white" : "text-ink-200 hover:bg-white/[0.05] hover:text-white",
                )}
              >
                <Icon
                  aria-hidden
                  className={cn("size-4 shrink-0", active ? "text-forest-200" : "text-ink-300 group-hover:text-ink-200")}
                />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function ActiveCompanyCard({ onNavigate }: { onNavigate?: () => void }) {
  const { activeCompany, runs } = useWorkspace();
  const runningCount = Object.values(runs).filter((r) => r.status === "running").length;
  if (!activeCompany) {
    return (
      <div className="rounded-md border border-dashed border-white/15 px-3 py-3 text-[12.5px] leading-relaxed text-ink-300">
        No company selected. Use the Company Explorer to choose one.
      </div>
    );
  }
  return (
    <Link
      href={withContext(routes.company, activeCompany)}
      onClick={onNavigate}
      className="block rounded-md bg-white/[0.05] px-3 py-2.5 ring-1 ring-white/10 transition-colors hover:bg-white/[0.08]"
    >
      <span className="block text-[11px] font-medium tracking-wider text-ink-300 uppercase">Active company</span>
      <span className="mt-1 block truncate text-[13.5px] font-semibold text-white">{activeCompany.name}</span>
      <span className="mt-0.5 block font-mono text-[12px] text-ink-200">
        {activeCompany.ticker} · {MARKETS[activeCompany.market].short}
      </span>
      {runningCount > 0 ? (
        <span className="mt-2 flex items-center gap-1.5 text-[12px] text-forest-200" role="status">
          <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-forest-200" />
          {runningCount === 1 ? "Assessment running" : `${runningCount} assessments running`}
        </span>
      ) : null}
    </Link>
  );
}

function SidebarContents({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <Link href="/" onClick={onNavigate} className="flex items-center gap-3 px-5 pt-5 pb-6">
        <BrandMark />
        <span className="leading-tight">
          <span className="block text-[14px] font-semibold tracking-tight text-white">ESG Integrity</span>
          <span className="block text-[12px] text-ink-300">Intelligence</span>
        </span>
      </Link>
      <div className="flex-1 overflow-y-auto px-3">
        <NavList onNavigate={onNavigate} />
      </div>
      <div className="space-y-3 px-3 pt-4 pb-5">
        <ActiveCompanyCard onNavigate={onNavigate} />
        <p className="px-1 text-[11px] leading-relaxed text-ink-300">
          Scores assess the substantiation of disclosed claims only. Not an ESG rating, audit, or greenwashing finding.
        </p>
      </div>
    </div>
  );
}

type Health = "checking" | "online" | "offline";

function BackendStatus() {
  const [health, setHealth] = useState<Health>("checking");
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const check = () =>
      api.health({ signal: controller.signal }).then(
        () => !cancelled && setHealth("online"),
        () => !cancelled && setHealth("offline"),
      );
    check();
    const id = setInterval(check, 60_000);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(id);
    };
  }, []);
  const label = health === "online" ? "API connected" : health === "offline" ? "API unreachable" : "Checking API";
  return (
    <span
      className="hidden items-center gap-2 rounded-full border border-line bg-surface px-2.5 py-1 text-[12px] text-text-muted sm:inline-flex"
      title={`Backend: ${getApiBaseUrl()}`}
      role="status"
    >
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          health === "online" ? "bg-forest-500" : health === "offline" ? "bg-danger" : "animate-pulse bg-ink-300",
        )}
      />
      {label}
    </span>
  );
}

function MarketSelector() {
  const { market, setMarket } = useWorkspace();
  const pathname = usePathname();
  const router = useRouter();
  return (
    <Segmented<MarketId>
      label="Market"
      value={market}
      onChange={(m) => {
        setMarket(m);
        if (pathname.startsWith(routes.explorer)) router.replace(withContext(routes.explorer, { market: m }));
      }}
      options={[
        { value: "us_sec", label: "US · SEC", description: MARKETS.us_sec.label },
        { value: "gh_gse", label: "GH · GSE", description: MARKETS.gh_gse.label },
      ]}
    />
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface px-3 py-2 text-sm font-medium focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 bg-ink-900 lg:block">
        <SidebarContents />
      </aside>

      <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-950/50 lg:hidden" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] bg-ink-900 shadow-pop focus:outline-none lg:hidden">
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <Dialog.Description className="sr-only">Primary application navigation</Dialog.Description>
            <Dialog.Close
              aria-label="Close navigation"
              className="absolute top-5 right-3 rounded-md p-1.5 text-ink-200 hover:bg-white/10 hover:text-white"
            >
              <X aria-hidden className="size-4" />
            </Dialog.Close>
            <SidebarContents onNavigate={() => setMobileOpen(false)} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-line bg-canvas/90 backdrop-blur supports-[backdrop-filter]:bg-canvas/75">
          <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-3 px-4 sm:px-6 lg:px-8">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className="-ml-1 rounded-md p-2 text-text-muted hover:bg-black/[0.05] hover:text-text lg:hidden"
              aria-label="Open navigation"
            >
              <Menu aria-hidden className="size-5" />
            </button>
            <Link href="/" className="flex items-center gap-2 lg:hidden">
              <BrandMark />
              <span className="hidden text-[14px] font-semibold whitespace-nowrap min-[420px]:inline">ESG Integrity</span>
            </Link>
            <div className="ml-auto flex items-center gap-3">
              <BackendStatus />
              <MarketSelector />
            </div>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 md:py-8 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
