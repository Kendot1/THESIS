"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

const Header = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const links = [
    { href: "/", label: "Home" },
    { href: "/Search", label: "Search" },
    { href: "/Table", label: "Table" },
    { href: "/About", label: "About" },
  ];

  return (
    <header role="banner">
      <nav
        aria-label="Main navigation"
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ease-out ${
          scrolled
            ? "py-2.5 bg-white/95 backdrop-blur-2xl shadow-[0_1px_24px_rgba(0,0,0,0.06)]"
            : "py-4 bg-white/90 backdrop-blur-xl"
        }`}
      >
        <div className="max-w-7xl mx-auto px-5 lg:px-10 flex items-center justify-between">
          {/* Logo */}
          <Link
            href="/"
            className="flex items-center gap-3 group"
            aria-label="FOODCAST home"
          >
            <img
              src="/FoodcastLogo.svg"
              alt="FOODCAST"
              width={120}
              height={40}
              className="transition-all duration-300 group-hover:scale-[1.03] group-hover:brightness-110"
            />
          </Link>

          {/* Desktop Nav */}
          <ul className="hidden md:flex items-center gap-1">
            {links.map((link) => {
              const isActive = pathname === link.href;
              return (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className={`relative px-4 py-2 rounded-full text-sm font-medium transition-all duration-300 ${
                      isActive
                        ? "text-primary-800 bg-primary-50/80"
                        : "text-gray-500 hover:text-primary-800 hover:bg-gray-50"
                    }`}
                    aria-current={isActive ? "page" : undefined}
                  >
                    {link.label}
                    {isActive && (
                      <span className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-5 h-[2.5px] rounded-full bg-orange" />
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>

          {/* CTA + Mobile Toggle */}
          <div className="flex items-center gap-3">
            <Link
              href="/Search"
              className="hidden sm:flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-orange to-orange-light text-white font-semibold rounded-full text-sm
                transition-all duration-300 hover:shadow-[0_4px_20px_rgba(255,145,77,0.35)] hover:-translate-y-[1px] active:translate-y-0"
            >
              Get Started
            </Link>

            <button
              className="md:hidden flex items-center justify-center w-10 h-10 rounded-xl bg-gray-100 hover:bg-gray-200 transition-all duration-200 active:scale-95"
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
          className={`md:hidden overflow-hidden transition-all duration-400 ease-out bg-white ${
            mobileOpen
              ? "max-h-96 opacity-100"
              : "max-h-0 opacity-0 pointer-events-none"
          }`}
          role="menu"
        >
          <div className="pt-4 pb-3 px-4">
            <ul className="flex flex-col gap-1">
              {links.map((link, i) => (
                <li key={link.href} role="none">
                  <Link
                    href={link.href}
                    onClick={() => setMobileOpen(false)}
                    role="menuitem"
                    className={`flex items-center px-4 py-3 rounded-2xl text-sm font-medium transition-all duration-250 ${
                      pathname === link.href
                        ? "text-primary-800 bg-primary-50"
                        : "text-gray-600 hover:text-gray-900 hover:bg-gray-50"
                    }`}
                    style={{ animationDelay: `${i * 60}ms` }}
                    aria-current={pathname === link.href ? "page" : undefined}
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
            <div className="mt-3 px-1">
              <Link
                href="/Search"
                onClick={() => setMobileOpen(false)}
                className="flex items-center justify-center w-full px-4 py-3 bg-gradient-to-r from-orange to-orange-light text-white font-semibold rounded-2xl text-sm transition-all hover:shadow-lg active:scale-[0.98]"
              >
                Get Started
              </Link>
            </div>
          </div>
        </div>
      </nav>
    </header>
  );
};

export default Header;