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
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const links = [
    { href: "/", label: "Home" },
    { href: "/Search", label: "Search" },
    { href: "/About", label: "About" },
    { href: "/Resources", label: "Resources" },
  ];

  return (
    <nav className={`nav-header ${scrolled ? "scrolled" : ""}`}>
      <Link href="/" className="nav-logo">
        FOODCAST
      </Link>
      <ul className="nav-links" style={mobileOpen ? { display: "flex", position: "absolute", top: "100%", left: 0, right: 0, flexDirection: "column", background: "rgba(11,59,36,0.98)", padding: "20px 48px", gap: "16px" } : undefined}>
        {links.map(link => (
          <li key={link.href}>
            <Link
              href={link.href}
              className={pathname === link.href ? "active" : ""}
              onClick={() => setMobileOpen(false)}
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
      <button className="mobile-menu-btn" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Toggle menu">
        {mobileOpen ? <X size={24} /> : <Menu size={24} />}
      </button>
    </nav>
  );
};

export default Header;