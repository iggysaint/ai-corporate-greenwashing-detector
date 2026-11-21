import { Compass } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/states";

export default function NotFound() {
  return (
    <EmptyState icon={Compass} title="Page not found" action={<ButtonLink href="/">Back to overview</ButtonLink>}>
      The page you requested does not exist.
    </EmptyState>
  );
}
