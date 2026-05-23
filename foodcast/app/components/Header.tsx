"use client";
import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, ChevronDown } from "lucide-react";

const Header = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const pathname = usePathname();
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
    setOpenDropdown(null);
  }, [pathname]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setOpenDropdown(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const links = [
    { href: "/", label: "Home" },
    { href: "/Predict", label: "Predict" },
    { href: "/MarketData", label: "Market Data" },
    { href: "/News", label: "News" },
    {
      label: "About",
      href: "/About",
      dropdown: [
        { href: "/About", label: "About Foodcast" },
        { href: "/Resources", label: "Resources" }
      ]
    },
  ];

  const toggleDropdown = (label: string) => {
    setOpenDropdown(openDropdown === label ? null : label);
  };

  return (
    <header role="banner">
      <nav
        aria-label="Main navigation"
        className={`fixed top-0 left-0 right-0 z-50 shadow-[0_1px_24px_rgba(0,0,0,0.15)] transition-all duration-500 ease-out ${scrolled
          ? "py-4 bg-surface/90 backdrop-blur-2xl" : "py-4 bg-surface backdrop-blur-xl"}`}
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
          <div className="flex items-center gap-6" ref={dropdownRef}>
            {/* Desktop Nav */}
            <ul className="hidden md:flex items-center gap-4">
              {links.map((link) => {
                const isActive = 
                  pathname === link.href || 
                  (link.dropdown && link.dropdown.some(d => d.href === pathname)) ||
                  (link.href === "/MarketData" && pathname.startsWith("/Product"));
                  
                const isDropdownOpen = openDropdown === link.label;

                if (link.dropdown) {
                  return (
                    <li
                      key={link.label}
                      className="relative group/dropdown"
                      onMouseEnter={() => setOpenDropdown(link.label)}
                      onMouseLeave={() => setOpenDropdown(null)}
                    >
                      <button
                        onClick={() => toggleDropdown(link.label)}
                        className={`
                          relative px-4 py-2 rounded-2xl text-sm font-medium flex items-center gap-1.5 transition-all duration-300
                          ${isActive || isDropdownOpen ? "text-primary-800" : "text-gray-500 hover:text-primary-800"}
                        `}
                        aria-haspopup="true"
                        aria-expanded={isDropdownOpen}
                      >
                        {link.label}
                        <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-300 ${isDropdownOpen ? "rotate-180" : ""}`} />
                        {(isActive || isDropdownOpen) && (
                          <span className="absolute left-0 bottom-0 w-full h-[3px] bg-orange-dark scale-x-100 origin-left transition-transform duration-300" />
                        )}
                      </button>

                      {/* Dropdown Menu */}
                      <div
                        className={`absolute top-full left-0 pt-3 w-48 transition-all duration-300 z-50
                          ${isDropdownOpen ? "opacity-100 translate-y-0 pointer-events-auto" : "opacity-0 translate-y-2 pointer-events-none"}
                        `}
                      >
                        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 py-2 overflow-hidden">
                          {link.dropdown.map((sub) => (
                            <Link
                              key={sub.href}
                              href={sub.href}
                              className={`block px-5 py-2.5 text-sm font-medium transition-colors hover:bg-gray-50
                                ${pathname === sub.href ? "text-primary-800 bg-primary-50/50" : "text-gray-600 hover:text-primary-800"}`}
                            >
                              {sub.label}
                            </Link>
                          ))}
                        </div>
                      </div>
                    </li>
                  );
                }

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
            ? "max-h-[600px] opacity-100"
            : "max-h-0 opacity-0 pointer-events-none"
            }`}
          role="menu"
        >
          <div className="pt-4 pb-10 px-4">
            <ul className="flex flex-col gap-3 items-center justify-center">
              {links.map((link, i) => {
                const isActive = 
                  pathname === link.href || 
                  (link.dropdown && link.dropdown.some(d => d.href === pathname)) ||
                  (link.href === "/MarketData" && pathname.startsWith("/Product"));

                if (link.dropdown) {
                  return (
                    <li key={link.label} className="w-full max-w-[280px] bg-white/40 rounded-3xl p-2 border border-black/5">
                      <div className="flex flex-col items-center">
                        <span className={`px-5 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-gray-400`}>
                          {link.label}
                        </span>
                        <div className="flex flex-col gap-2 w-full mt-1">
                          {link.dropdown.map((sub) => (
                            <Link
                              key={sub.href}
                              href={sub.href}
                              onClick={() => setMobileOpen(false)}
                              className={`px-5 py-3 rounded-2xl text-sm font-medium text-center transition-all duration-300
                                ${pathname === sub.href ? "bg-primary-100/50 text-primary-900" : "text-gray-600 hover:bg-gray-50"}`}
                            >
                              {sub.label}
                            </Link>
                          ))}
                        </div>
                      </div>
                    </li>
                  );
                }

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
                          : `text-primary-800 bg-primary-50/50`
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
          </div>
        </div>
      </nav>
    </header>
  );
};

export default Header;