import { BookOpenText, Building2, FileSearch, Gauge, History, LayoutGrid } from "lucide-react";
import { routes } from "@/lib/routes";

export const NAV_ITEMS = [
  { href: routes.overview, label: "Overview", icon: LayoutGrid, needsCompany: false },
  { href: routes.explorer, label: "Company Explorer", icon: Building2, needsCompany: false },
  { href: routes.assessment, label: "ESG Assessments", icon: Gauge, needsCompany: true },
  { href: routes.claims, label: "Claims & Evidence", icon: FileSearch, needsCompany: true },
  { href: routes.history, label: "Assessment History", icon: History, needsCompany: true },
  { href: routes.methodology, label: "Methodology", icon: BookOpenText, needsCompany: false },
] as const;
