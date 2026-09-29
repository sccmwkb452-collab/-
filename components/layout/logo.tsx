import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

interface LogoProps {
  name: string;
  logoUrl?: string | null;
  inverted?: boolean;
  className?: string;
}

export function Logo({ name, logoUrl, inverted, className }: LogoProps) {
  return (
    <Link href="/" className={cn("group flex items-center gap-2.5 rounded-md", className)} aria-label={`${name} — на главную`}>
      {logoUrl ? (
        <Image src={logoUrl} alt={name} width={140} height={36} className="h-8 w-auto object-contain" unoptimized={logoUrl.endsWith(".svg")} />
      ) : (
        <>
          <svg viewBox="0 0 32 32" className={cn("size-8 transition-transform duration-500 group-hover:rotate-[-4deg]", inverted ? "text-white" : "text-primary")} aria-hidden>
            <rect x="1" y="1" width="30" height="30" rx="8" fill="currentColor" />
            <path d="M8 23V14.5L16 8l8 6.5V23" fill="none" stroke="var(--brand-accent)" strokeWidth="2.2" strokeLinejoin="round" />
            <path d="M13 23v-5h6v5" fill="none" stroke={inverted ? "#171717" : "#F7F6F2"} strokeWidth="2.2" strokeLinejoin="round" />
          </svg>
          <span className={cn("text-[15px] font-extrabold tracking-[0.14em] uppercase", inverted ? "text-white" : "text-foreground")}>{name}</span>
        </>
      )}
    </Link>
  );
}
