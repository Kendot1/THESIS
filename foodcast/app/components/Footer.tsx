"use client";
import Link from "next/link";
import Image from "next/image";
import { Home, Search, Table2, Info, Mail, MapPin, TrendingUp } from "lucide-react";
import GrassField from "./GrassField";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { usePathname } from "next/navigation";

const Footer = () => {
  const { t, isTransitioning } = useLanguage();
  const currentYear = new Date().getFullYear();
  const pathname = usePathname();

  if (pathname === '/Map') {
    return null;
  }

  // --- Skeleton for language transition ---
  if (isTransitioning) {
    return (
      <footer className="bg-primary-800 relative" role="contentinfo">
        <div className="relative max-w-7xl mx-auto px-5 lg:px-10 pt-12 pb-8">
          <div className="grid md:grid-cols-3 gap-10 lg:gap-16 mb-14">
            <div className="md:col-span-1">
              <div className="w-[130px] h-[50px] bg-white/10 rounded-2xl mb-6 skeleton-shimmer-dark" />
              <div className="space-y-2 mb-6 max-w-xs">
                <div className="h-3 w-full bg-white/10 rounded skeleton-shimmer-dark" />
                <div className="h-3 w-5/6 bg-white/10 rounded skeleton-shimmer-dark" style={{ animationDelay: "80ms" }} />
                <div className="h-3 w-4/6 bg-white/10 rounded skeleton-shimmer-dark" style={{ animationDelay: "160ms" }} />
              </div>
              <div className="flex gap-6">
                {[1, 2].map(i => (
                  <div key={i} className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-white/10 skeleton-shimmer-dark" />
                    <div className="space-y-1">
                      <div className="h-3 w-10 bg-white/10 rounded skeleton-shimmer-dark" />
                      <div className="h-2 w-14 bg-white/10 rounded skeleton-shimmer-dark" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="h-4 w-24 bg-white/10 rounded mb-6 skeleton-shimmer-dark" />
              <div className="space-y-3">
                {[1, 2, 3, 4, 5].map(i => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-white/5 rounded-lg skeleton-shimmer-dark" style={{ animationDelay: `${i * 60}ms` }} />
                    <div className="h-3 w-20 bg-white/10 rounded skeleton-shimmer-dark" style={{ animationDelay: `${i * 60}ms` }} />
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="h-4 w-32 bg-white/10 rounded mb-6 skeleton-shimmer-dark" />
              <div className="space-y-2 mb-5">
                <div className="h-3 w-full bg-white/10 rounded skeleton-shimmer-dark" />
                <div className="h-3 w-5/6 bg-white/10 rounded skeleton-shimmer-dark" style={{ animationDelay: "80ms" }} />
                <div className="h-3 w-3/4 bg-white/10 rounded skeleton-shimmer-dark" style={{ animationDelay: "160ms" }} />
              </div>
              <div className="h-3 w-44 bg-white/10 rounded skeleton-shimmer-dark" />
            </div>
          </div>
          <div className="relative pt-6">
            <div className="absolute inset-x-0 top-0 h-px bg-white/5" />
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="h-2.5 w-64 bg-white/10 rounded skeleton-shimmer-dark" />
              <div className="h-2.5 w-40 bg-white/10 rounded skeleton-shimmer-dark" />
            </div>
          </div>
        </div>
      </footer>
    );
  }

  const navLinks = [
    { href: "/", label: t("home"), icon: <Home className="w-4 h-4" /> },
    { href: "/Predict", label: t("predict"), icon: <TrendingUp className="w-4 h-4" /> },
    { href: "/MarketData", label: t("marketData"), icon: <Table2 className="w-4 h-4" /> },
    { href: "/Resources", label: t("resources"), icon: <Mail className="w-4 h-4" /> },
    { href: "/About", label: t("about"), icon: <Info className="w-4 h-4" /> },
  ];

  return (
    <footer className="relative overflow-hidden" role="contentinfo">
      {/* ─── Farm Grass Field Animation ─── */}
      <GrassField />

      {/* ─── Footer Body ───────────────────────────── */}
      <div className="bg-primary-800 relative">
        <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
          <div className="absolute -top-20 left-1/4 w-[450px] h-[20px] bg-accent/4 rounded-full blur-[100px]" />
        </div>

        <div className="relative max-w-7xl mx-auto px-5 lg:px-10 pt-12 pb-8">
          <div className="grid md:grid-cols-3 gap-10 lg:gap-16 mb-14">
            {/* Brand Column */}
            <div className="md:col-span-1">
              <div className="inline-flex items-center justify-center p-3 bg-white/80 rounded-2xl mb-6 backdrop-blur-sm
                transition-all duration-300">
                <Image src="/FoodcastLogo.svg" alt="FOODCAST" width={130} height={60} />
              </div>
              <p className="text-white/60 text-xs sm:text-sm leading-relaxed max-w-xs mb-6">
                {t("footerDesc")}
              </p>
              <div className="flex gap-6">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                    <TrendingUp className="w-4 h-4 text-accent" />
                  </div>
                  <div>
                    <div className="text-white/80 text-xs font-semibold">98.5%</div>
                    <div className="text-white/60 text-[10px]">{t("accuracy")}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                    <MapPin className="w-4 h-4 text-accent" />
                  </div>
                  <div>
                    <div className="text-white/80 text-xs font-semibold">NCR</div>
                    <div className="text-white/60 text-[10px]">{t("coverage")}</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Navigation Column */}
            <div>
              <h4 className="text-white/80 font-semibold mb-4 sm:mb-6 text-sm uppercase tracking-wider" style={{ fontFamily: "var(--font-display)" }}>
                {t("quickLinks")}
              </h4>
              <nav aria-label="Footer navigation">
                <ul className="grid grid-cols-2 sm:grid-cols-1 gap-3">
                  {navLinks.map((link) => (
                    <li key={link.href}>
                      <Link href={link.href} className="group flex items-center gap-3 text-white/60 text-xs sm:text-sm transition-all duration-300 hover:text-accent hover:translate-x-1">
                        <span className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center text-white/60 group-hover:bg-accent/15 group-hover:text-accent transition-all duration-300">
                          {link.icon}
                        </span>
                        <span className="font-medium">{link.label}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </nav>
            </div>

            {/* About Column */}
            <div>
              <h4 className="text-white font-semibold mb-4 sm:mb-6 text-white/80 text-sm uppercase tracking-wider" style={{ fontFamily: "var(--font-display)" }}>
                {t("aboutProject")}
              </h4>
              <p className="text-white/60 text-xs sm:text-sm leading-relaxed mb-5">
                {t("footerAboutDesc")}
              </p>
              <div className="flex items-center gap-2 text-white/40 text-[10px] sm:text-xs">
                <Mail className="w-3.5 h-3.5" />
                <span>foodcast.thesis@gmail.com</span>
              </div>
            </div>
          </div>

          {/* Divider + Copyright */}
          <div className="relative pt-6">
            <div className="absolute inset-x-0 top-0 h-px"
              style={{ background: "linear-gradient(to right, transparent, rgba(126,217,87,0.15), rgba(255,255,255,0.08), rgba(126,217,87,0.15), transparent)" }}
              aria-hidden="true"
            />
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
              <p className="text-white/35 text-[10px] sm:text-[11px]">© {currentYear} FOODCAST — AgriTech Food Forecast. {t("allRightsReserved")}</p>
              <div className="flex items-center gap-1.5 text-white/30 text-[9px] sm:text-[10px]">
                <div className="w-1.5 h-1.5 rounded-full bg-accent/40 animate-pulse" />
                <span>{t("poweredBy")}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;