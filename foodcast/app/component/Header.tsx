"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";

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
    { href: "/Predict", label: "Predict" },
    { href: "/About", label: "About" },
    { href: "/Resources", label: "Resources" },
  ];

  return (
    <header role="banner">
      <nav
        aria-label="Main navigation"
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ease-out ${scrolled
          ? "py-4 bg-surface/90 backdrop-blur-2xl shadow-[0_1px_24px_rgba(0,0,0,0.15)]"
          : "py-4 bg-surface/90 backdrop-blur-xl"
          }`}
      >
        <div className="max-w-7xl mx-auto px-5 lg:px-10 flex items-center justify-between">
          {/* Logo */}
          <Link
            href="/"
            className="flex items-center gap-3"
            aria-label="FOODCAST home"
          >
            <img
              src="/FoodcastLogo.svg"
              alt="FOODCAST"
              width={180}
              height={50}
              className="transition-all duration-300 group-hover:scale-[1.03] group-hover:brightness-110"
            />
          </Link>

          {/* RIGHT SIDE: Desktop Links + Mobile Toggle */}
          <div className="flex items-center gap-6">
            {/* Desktop Nav */}
            <ul className="hidden md:flex items-center gap-4">
              {links.map((link) => {
                const isActive = pathname === link.href;

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
                          text-gray-500 hover:text-primary-800
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

            {/* Mobile Toggle */}
            <button
              className="md:hidden flex items-center justify-center w-10 h-10 
              rounded-xl bg-transparent hover:bg-[#d2c5b6] transition-all duration-200 active:scale-95 "
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
            ? "max-h-96 opacity-100"
            : "max-h-0 opacity-0 pointer-events-none"
            }`}
          role="menu"
        >
          <div className="pt-4 pb-3 px-4">
            <ul className="flex flex-col gap-3 items-center justify-center">
              {links.map((link, i) => {
                const isActive = pathname === link.href;

                return (
                  <li key={link.href} role="none">
                    <Link
                      href={link.href}
                      onClick={() => setMobileOpen(false)}
                      role="menuitem"
                      className={`relative px-5 py-3 rounded-2xl text-sm font-medium block transition-all duration-300
                        ${!isActive
                          ? `
                            text-gray-600 hover:text-gray-900 hover:bg-gray-50
                            after:absolute after:bottom-0 after:left-0 after:h-[3px] after:bg-orange-dark
                            after:w-full after:scale-x-0 hover:after:scale-x-100 after:transition-transform after:duration-300 after:origin-center
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
                        <span className="absolute bottom-0 left-0 w-full h-[3px] bg-orange-dark
                          scale-x-100 origin-left transition-transform duration-300"/>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </nav>
    </header>
  );
};

export default Header;