"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { Menu, X, Globe } from "lucide-react";
import { useLanguage } from "../lib/i18n/LanguageContext";

export default function Header() {
  const { language, setLanguage, t, isTransitioning } = useLanguage();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  const normalizedPathname = pathname.replace(/\/$/, "").toLowerCase() || "/";
  const isPredictSection = normalizedPathname === "/predict"
    || normalizedPathname === "/marketdata"
    || normalizedPathname.startsWith("/product/");
  const isNewsSection = normalizedPathname === "/news"
    || normalizedPathname.startsWith("/tags/");
  const isActiveLink = (href: string) => {
    if (href === "/Predict") return isPredictSection;
    if (href === "/News") return isNewsSection;
    return normalizedPathname === href.toLowerCase();
  };

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const links = [
    { href: "/", label: t("home") },
    { href: "/Predict", label: t("predict") },
    { href: "/News", label: t("news") },
    { href: "/Map", label: t("marketMap") },
    { href: "/About", label: t("about") },
    { href: "/Resources", label: t("resources") },
  ];

  // --- Skeleton for language transition ---
  if (isTransitioning) {
    return (
      <header role="banner">
        <nav className="fixed top-0 left-0 right-0 z-[100] py-4 bg-surface shadow-[0_1px_24px_rgba(0,0,0,0.15)]">
          <div className="max-w-7xl mx-auto px-5 lg:px-10 flex items-center justify-between">
            <div className="h-8 w-[140px] bg-gray-200 rounded-lg skeleton-shimmer" />
            <div className="hidden md:flex items-center gap-4">
              {[80, 60, 90, 50, 60].map((w, i) => (
                <div key={i} className="h-5 rounded-lg bg-gray-200 skeleton-shimmer" style={{ width: w, animationDelay: `${i * 80}ms` }} />
              ))}
              <div className="ml-6 pl-6 border-l border-gray-100">
                <div className="h-8 w-16 bg-gray-200 rounded-xl skeleton-shimmer" style={{ animationDelay: "400ms" }} />
              </div>
            </div>
            <div className="md:hidden w-10 h-10 bg-gray-200 rounded-xl skeleton-shimmer" />
          </div>
        </nav>
      </header>
    );
  }

  return (
    <header role="banner">
      <nav
        aria-label="Main navigation"
        className={`fixed top-0 left-0 right-0 z-[100] shadow-[0_1.5px_24px_rgba(0,0,0,0.15)] 
          transition-all duration-500 ease-out ${scrolled
            ? "py-4 bg-surface" : "py-4 bg-surface"}`}
      >
        <div className="max-w-7xl mx-auto px-5 lg:px-10 flex items-center justify-between">
          {/* Logo */}
          <Link
            href="/"
            className="flex items-center gap-3"
            aria-label="FOODCAST home"
          >
            <Image
              src="/FoodcastLogo.svg"
              alt="FOODCAST"
              width={180}
              height={50}
              className="transition-all duration-300 group-hover:scale-[1.03] group-hover:brightness-110"
              priority
            />
          </Link>

          {/* RIGHT SIDE: Desktop Links + Mobile Toggle */}
          <div className="flex items-center gap-6">
            {/* Desktop Nav */}
            <ul className="hidden md:flex items-center gap-4">
              {links.map((link) => {
                const isActive = isActiveLink(link.href);

                return (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className={`
                        relative px-4 py-2 rounded-2xl text-sm font-medium w-fit block
                        transition-all duration-300

                        ${!isActive ? `
                          after:absolute after:left-0 after:bottom-0 after:h-[3px]
                          after:bg-orange-dark after:w-full after:scale-x-0
                          hover:after:scale-x-100 after:transition after:duration-300 after:origin-center
                          text-gray-700 hover:text-primary-800
                        ` : `
                          text-primary-800
                        `}
                      `}
                    >
                      {link.label}

                      {/* ACTIVE underline */}
                      {isActive && (
                        <span className="
                          absolute left-0 bottom-0 w-full h-[3px] bg-orange-dark
                          scale-x-100 origin-left transition-transform duration-300
                        " />
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>

            <div className="hidden md:flex items-center gap-3 ml-6 pl-6 border-l border-gray-200">
              {/* Language Toggle */}
              <button
                onClick={() => setLanguage(language === "en" ? "tl" : "en")}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl 
                bg-gray-50 border border-gray-300 text-sm font-bold text-gray-700 
                hover:bg-gray-100 hover:text-primary-800 transition-colors"
                aria-label="Toggle Language"
              >
                <Globe className="w-4 h-4 text-gray-400" />
                {language === "en" ? "EN" : "FIL"}
              </button>
            </div>

            {/* Mobile Toggle */}
            <button
              className="md:hidden flex items-center justify-center w-10 h-10 
              rounded-xl bg-transparent hover:bg-[#d2c5b6] transition-all duration-200 active:scale-95 ml-auto"
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
              aria-expanded={mobileOpen}
              aria-controls="mobile-menu"
            >
              {mobileOpen ? (
                <X className="w-5 h-5 text-gray-700" />
              ) : (
                <Menu className="w-5 h-5 text-gray-700" />
              )}
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        <div
          id="mobile-menu"
          className={`md:hidden overflow-hidden transition-all duration-400 ease-out bg-transparent ${mobileOpen
            ? "max-h-[600px] opacity-100"
            : "max-h-0 opacity-0 pointer-events-none"
            }`}
          role="menu"
        >
          <div className="pt-4 pb-10 px-4">
            <ul className="flex flex-col gap-3 items-center justify-center">
              {links.map((link, i) => {
                const isActive = isActiveLink(link.href);

                return (
                  <li key={link.href} role="none" className="w-full max-w-[280px]">
                    <Link
                      href={link.href}
                      onClick={() => setMobileOpen(false)}
                      role="menuitem"
                      className={`relative px-5 py-3 rounded-2xl text-sm font-medium block text-center transition-all duration-300
                        ${!isActive
                          ? `
                            text-gray-600 hover:text-gray-900 hover:bg-gray-50
                            after:absolute after:bottom-0 after:left-1/4 after:h-[3px] after:bg-orange-dark
                            after:w-1/2 after:scale-x-0 hover:after:scale-x-100 after:transition-transform after:duration-300 after:origin-center
                          `
                          : `text-primary-800`
                        }
                      `}
                      style={{ animationDelay: `${i * 60}ms` }}
                      aria-current={isActive ? "page" : undefined}
                    >
                      {link.label}

                      {/* ACTIVE underline */}
                      {isActive && (
                        <span className="absolute bottom-0 left-1/4 w-1/2 h-[3px] bg-orange-dark
                          scale-x-100 origin-center transition-transform duration-300"/>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>

            <div className="mt-8 pt-6 border-t border-gray-100 flex justify-center">
              <button
                onClick={() => {
                  setLanguage(language === "en" ? "tl" : "en");
                  setMobileOpen(false);
                }}
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-white border border-gray-200 text-sm font-bold text-gray-700 shadow-sm active:scale-95 transition-all"
              >
                <Globe className="w-5 h-5 text-gray-400" />
                {language === "en" ? "Switch to Filipino (FIL)" : "Switch to English (EN)"}
              </button>
            </div>
          </div>
        </div>
      </nav>
    </header>
  );
};
