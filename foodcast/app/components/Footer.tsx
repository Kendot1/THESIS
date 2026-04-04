"use client";
import Link from "next/link";
import { Home, Search, Table2, Info, Mail, MapPin, TrendingUp } from "lucide-react";

const Footer = () => {
  const currentYear = new Date().getFullYear();

  const navLinks = [
    { href: "/", label: "Home", icon: <Home className="w-4 h-4" /> },
    { href: "/Search", label: "Search", icon: <Search className="w-4 h-4" /> },
    { href: "/Table", label: "Table", icon: <Table2 className="w-4 h-4" /> },
    { href: "/About", label: "About", icon: <Info className="w-4 h-4" /> },
  ];

  // Seeded pseudo-random for consistent SSR / CSR rendering
  const seededRandom = (seed: number) => {
    const x = Math.sin(seed * 9301 + 49297) * 49297;
    return x - Math.floor(x);
  };

  // ─── Massive Grass Generation ──────────────────────
  interface GrassBlade {
    x: number;
    height: number;
    curve: number;
    width: number;
    color: string;
    delay: number;
    duration: number;
  }

  const TOTAL_BLADES = 800;
  const blades: GrassBlade[] = [];

  for (let i = 0; i < TOTAL_BLADES; i++) {
    const r = seededRandom(i);
    const r2 = seededRandom(i + 200);
    const r3 = seededRandom(i + 400);
    const r4 = seededRandom(i + 600);
    const r5 = seededRandom(i + 800);

    const x = (i / TOTAL_BLADES) * 1440 + (r - 0.5) * 12;
    const height = 25 + r2 * 140;
    const curve = (r3 - 0.5) * 30;
    const width = 0.5 + r4 * 3;

    // Lush farm greens
    const shade = r5;
    const color =
      shade > 0.93 ? "#AED581" :
        shade > 0.84 ? "#9CCC65" :
          shade > 0.72 ? "#8BC34A" :
            shade > 0.58 ? "#7CB342" :
              shade > 0.44 ? "#66BB6A" :
                shade > 0.3 ? "#4CAF50" :
                  shade > 0.18 ? "#43A047" :
                    shade > 0.08 ? "#2E7D32" :
                      "#1B5E20";

    const duration = 5 + r2 * 12;
    const delay = r * 10;

    blades.push({ x, height, curve, width, color, delay, duration });
  }

  // Render a grass blade as a cubic bezier
  const renderBlade = (
    b: GrassBlade,
    i: number,
    prefix: string,
    heightMult: number,
    opacityBase: number,
    widthMult: number,
    colorOverride?: string
  ) => {
    const baseY = 300;
    const h = b.height * heightMult;
    const tipY = baseY - h;
    const cp1X = b.x + b.curve * 0.25;
    const cp1Y = baseY - h * 0.35;
    const cp2X = b.x + b.curve * 0.75;
    const cp2Y = baseY - h * 0.72;
    const tipX = b.x + b.curve * 0.5;
    const opacity = opacityBase + seededRandom(i + 3000) * 0.15;

    return (
      <path
        key={`${prefix}-${i}`}
        d={`M${b.x},${baseY} C${cp1X},${cp1Y} ${cp2X},${cp2Y} ${tipX},${tipY}`}
        stroke={colorOverride || b.color}
        strokeWidth={b.width * widthMult}
        fill="none"
        strokeLinecap="round"
        opacity={Math.min(opacity, 1)}
        style={{
          transformOrigin: `${b.x}px ${baseY}px`,
          animation: `grassSway ${b.duration}s ease-in-out ${b.delay}s infinite`,
        }}
      />
    );
  };

  // Wildflowers
  const flowers = Array.from({ length: 15 }, (_, i) => {
    const r = seededRandom(i + 7000);
    const r2 = seededRandom(i + 7200);
    const r3 = seededRandom(i + 7400);
    return {
      x: r * 1440,
      y: 210 + r2 * 70,
      color: r3 > 0.7 ? "#FFF9C4" : r3 > 0.5 ? "#FFFFFF" : r3 > 0.3 ? "#F8BBD0" : "#CE93D8",
      size: 1.5 + r * 2.5,
    };
  });

  // Butterflies
  const butterflies = Array.from({ length: 3 }, (_, i) => {
    const r = seededRandom(i + 5000);
    const startX = 200 + r * 1000;
    const startY = 60 + seededRandom(i + 5100) * 120;
    return { startX, startY, delay: i * 4, duration: 14 + r * 8, size: 3 + r * 2 };
  });

  // Dandelion seeds
  const dandelions = Array.from({ length: 6 }, (_, i) => {
    const r = seededRandom(i + 6000);
    const r2 = seededRandom(i + 6200);
    return {
      startX: r * 1440,
      startY: 30 + r2 * 150,
      delay: i * 3,
      duration: 18 + r * 12,
      size: 1 + r * 1.5,
    };
  });

  return (
    <footer className="relative overflow-hidden" role="contentinfo">
      {/* ─── Pure Grass Field — No background, just blades ─── */}
      <div
        className="relative w-full h-[280px] sm:h-[340px] lg:h-[400px] bg-surface"
        aria-hidden="true"
      >
        {/* === Layer 1: Very far distant hazy grass === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full">
          {blades
            .filter((_, i) => i % 6 === 0)
            .map((b, i) => renderBlade(b, i, "L1", 0.2, 0.06, 0.35, "#86b57a"))}
        </svg>

        {/* === Layer 2: Far background === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full">
          {blades
            .filter((_, i) => i % 5 === 0)
            .map((b, i) => renderBlade(b, i, "L2", 0.3, 0.1, 0.45, "#6a9e5e"))}
        </svg>

        {/* === Layer 3: Mid-far === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full">
          {blades
            .filter((_, i) => i % 4 === 0)
            .map((b, i) => renderBlade(b, i, "L3", 0.4, 0.15, 0.6))}
        </svg>

        {/* === Layer 4: Middle grass === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full">
          {blades
            .filter((_, i) => i % 3 === 0)
            .map((b, i) => renderBlade(b, i, "L4", 0.55, 0.25, 0.75))}
        </svg>

        {/* === Layer 5: Main dense grass (ALL blades) === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full">
          {blades.map((b, i) => renderBlade(b, i, "L5", 0.7, 0.45, 0.9))}
        </svg>

        {/* === Layer 6: Foreground prominent blades === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full">
          {blades
            .filter((_, i) => i % 2 === 0)
            .map((b, i) => renderBlade(b, i, "L6", 0.9, 0.6, 1.05))}
        </svg>

        {/* === Layer 7: Closest dark silhouette blades === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full z-[2]">
          {blades
            .filter((_, i) => i % 3 === 0)
            .map((b, i) => {
              const baseY = 300;
              const h = b.height * 0.45;
              const tipY = baseY - h;
              return (
                <path
                  key={`dark-${i}`}
                  d={`M${b.x},${baseY} C${b.x + b.curve * 0.2},${baseY - h * 0.4} ${b.x + b.curve * 0.65},${baseY - h * 0.75} ${b.x + b.curve * 0.4},${tipY}`}
                  stroke="#0B3D2E"
                  strokeWidth={b.width * 1.2}
                  fill="none"
                  strokeLinecap="round"
                  opacity={0.45}
                  style={{
                    transformOrigin: `${b.x}px ${baseY}px`,
                    animation: `grassSway ${b.duration * 0.85}s ease-in-out ${b.delay + 0.5}s infinite`,
                  }}
                />
              );
            })}
        </svg>

        {/* === Wildflowers === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full z-[3]">
          {flowers.map((f, i) => (
            <g key={`flower-${i}`} style={{ animation: `grassSway ${7 + i * 0.4}s ease-in-out ${i * 0.6}s infinite` }}>
              <circle cx={f.x} cy={f.y} r={f.size} fill={f.color} opacity={0.55} />
              <circle cx={f.x - f.size * 0.7} cy={f.y - f.size * 0.25} r={f.size * 0.5} fill={f.color} opacity={0.35} />
              <circle cx={f.x + f.size * 0.7} cy={f.y - f.size * 0.25} r={f.size * 0.5} fill={f.color} opacity={0.35} />
              <circle cx={f.x} cy={f.y} r={f.size * 0.25} fill="#FFD54F" opacity={0.6} />
            </g>
          ))}
        </svg>

        {/* === Butterflies with flapping wings === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full z-[4]">
          {butterflies.map((bf, i) => (
            <g key={`bf-${i}`} style={{
              animation: `butterflyFloat ${bf.duration}s ease-in-out ${bf.delay}s infinite`,
              transformOrigin: `${bf.startX}px ${bf.startY}px`,
            }}>
              <ellipse cx={bf.startX} cy={bf.startY} rx={bf.size * 0.25} ry={bf.size * 0.7} fill="#FFFDE7" opacity={0.6} />
              <ellipse cx={bf.startX - bf.size} cy={bf.startY - bf.size * 0.2} rx={bf.size} ry={bf.size * 0.5}
                fill={i % 2 === 0 ? "#FFB74D" : "#81D4FA"} opacity={0.45}>
                <animate attributeName="rx" values={`${bf.size};${bf.size * 0.2};${bf.size}`} dur="0.35s" repeatCount="indefinite" />
              </ellipse>
              <ellipse cx={bf.startX + bf.size} cy={bf.startY - bf.size * 0.2} rx={bf.size} ry={bf.size * 0.5}
                fill={i % 2 === 0 ? "#FFB74D" : "#81D4FA"} opacity={0.45}>
                <animate attributeName="rx" values={`${bf.size};${bf.size * 0.2};${bf.size}`} dur="0.35s" repeatCount="indefinite" />
              </ellipse>
            </g>
          ))}
        </svg>

        {/* === Floating dandelion seeds === */}
        <svg viewBox="0 0 1440 300" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" className="absolute bottom-0 left-0 w-full h-full z-[5]">
          {dandelions.map((d, i) => (
            <g key={`seed-${i}`} style={{
              animation: `dandelionFloat ${d.duration}s linear ${d.delay}s infinite`,
              transformOrigin: `${d.startX}px ${d.startY}px`,
            }}>
              <line x1={d.startX} y1={d.startY} x2={d.startX} y2={d.startY + d.size * 3} stroke="#888" strokeWidth="0.3" opacity={0.3} />
              <circle cx={d.startX} cy={d.startY} r={d.size} fill="white" opacity={0.2} />
              <circle cx={d.startX - d.size * 0.4} cy={d.startY - d.size * 0.35} r={d.size * 0.35} fill="white" opacity={0.15} />
              <circle cx={d.startX + d.size * 0.4} cy={d.startY - d.size * 0.35} r={d.size * 0.35} fill="white" opacity={0.15} />
            </g>
          ))}
        </svg>

        {/* Ground / soil at the very bottom */}
        <div className="absolute bottom-0 left-0 right-0 h-[50px] z-[6]"
          style={{
            background: "linear-gradient(to top, #0B3D2E 0%, #14503b 35%, #2E7D32 70%, rgba(46,125,50,0) 100%)",
          }}
        />

        {/* Seamless fade into dark footer body */}
        <div className="absolute bottom-0 left-0 right-0 h-[65px] z-[7]"
          style={{
            background: "linear-gradient(to top, #0B3D2E 0%, rgba(11,61,46,0.95) 30%, rgba(11,61,46,0.5) 60%, transparent 100%)",
          }}
        />
      </div>

      {/* ─── Footer Body ───────────────────────────── */}
      <div className="bg-primary-800 relative">
        <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
          <div className="absolute -top-20 left-1/4 w-[400px] h-[200px] bg-accent/4 rounded-full blur-[100px]" />
        </div>

        <div className="relative max-w-7xl mx-auto px-5 lg:px-10 pt-12 pb-8">
          <div className="grid md:grid-cols-3 gap-12 lg:gap-16 mb-14">
            {/* Brand Column */}
            <div className="md:col-span-1">
              <div className="inline-flex items-center justify-center px-5 py-3 bg-white/8 border border-white/8 rounded-2xl mb-6 backdrop-blur-sm
                transition-all duration-300 hover:bg-white/12 hover:border-accent/15">
                <img src="/FoodcastLogo.svg" alt="FOODCAST" width={130} height={44} className="brightness-[10]" />
              </div>
              <p className="text-white/40 text-sm leading-relaxed max-w-xs mb-6">
                AI-Based Forecasting and Market Analysis of Agri-Fishery Food Prices
                in NCR Markets using Machine Learning Algorithms.
              </p>
              <div className="flex gap-6">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                    <TrendingUp className="w-4 h-4 text-accent" />
                  </div>
                  <div>
                    <div className="text-white text-xs font-bold">98.5%</div>
                    <div className="text-white/30 text-[10px]">Accuracy</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-orange/10 flex items-center justify-center">
                    <MapPin className="w-4 h-4 text-orange" />
                  </div>
                  <div>
                    <div className="text-white text-xs font-bold">NCR</div>
                    <div className="text-white/30 text-[10px]">Coverage</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Navigation Column */}
            <div>
              <h4 className="text-white font-bold mb-6 text-sm uppercase tracking-wider" style={{ fontFamily: "var(--font-display)" }}>
                Quick Links
              </h4>
              <nav aria-label="Footer navigation">
                <ul className="space-y-3">
                  {navLinks.map((link) => (
                    <li key={link.href}>
                      <Link href={link.href} className="group flex items-center gap-3 text-white/45 text-sm transition-all duration-300 hover:text-accent hover:translate-x-1">
                        <span className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center text-white/25 group-hover:bg-accent/15 group-hover:text-accent transition-all duration-300">
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
              <h4 className="text-white font-bold mb-6 text-sm uppercase tracking-wider" style={{ fontFamily: "var(--font-display)" }}>
                About the Project
              </h4>
              <p className="text-white/40 text-sm leading-relaxed mb-5">
                FOODCAST is a thesis project that leverages machine learning to help
                consumers, vendors, and policymakers anticipate food price movements
                in the Philippines&apos; NCR.
              </p>
              <div className="flex items-center gap-2 text-white/30 text-xs">
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
              <p className="text-white/20 text-xs">© {currentYear} FOODCAST — AgriTech Food Forecast. All rights reserved.</p>
              <div className="flex items-center gap-1.5 text-white/15 text-[10px]">
                <div className="w-1.5 h-1.5 rounded-full bg-accent/40 animate-pulse" />
                <span>Powered by Machine Learning</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;