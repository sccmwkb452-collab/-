import {
  Activity,
  BadgeCheck,
  Check,
  CreditCard,
  Gift,
  Headphones,
  LifeBuoy,
  Lock,
  Package,
  Receipt,
  Rocket,
  ShieldCheck,
  Sparkles,
  Timer,
  User,
  Zap,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  activity: Activity,
  badge: BadgeCheck,
  check: Check,
  card: CreditCard,
  gift: Gift,
  headphones: Headphones,
  "life-buoy": LifeBuoy,
  lock: Lock,
  package: Package,
  receipt: Receipt,
  rocket: Rocket,
  shield: ShieldCheck,
  sparkles: Sparkles,
  timer: Timer,
  user: User,
  zap: Zap,
};

/** Icons referenced by name from admin-editable content. */
export function NamedIcon({ name, className }: { name: string; className?: string }) {
  const Cmp = ICONS[name] ?? Sparkles;
  return <Cmp className={className} aria-hidden />;
}
