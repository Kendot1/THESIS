"use client";
import { useState } from "react";
import {
  Brain,
  Database,
  BarChart3,
  Cpu,
  LineChart,
  Shield,
  Users,
  TrendingUp,
  Layers,
  Target,
  X,
  ChevronRight,
} from "lucide-react";
import { Drawer } from "vaul";
import Header from "../component/Header";
import Footer from "../component/Footer";
import WaveDivider from "../component/WaveDivider";
import ScrollReveal from "../component/ScrollReveal";

const methodologySteps = [
  {
    step: 1,
    icon: <Database className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Data Collection",
    description:
      "Gathering historical price data from NCR markets including daily prices, supply volumes, weather patterns, and seasonal trends across multiple commodities.",
  },
  {
    step: 2,
    icon: <Layers className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Data Preparation",
    description:
      "Cleaning and organizing raw market data. We handle missing information and identify key factors to prepare the data for the AI system.",
  },
  {
    step: 3,
    icon: <Cpu className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "AI Analysis",
    description:
      "Using advanced forecasting technology and market pattern recognition to analyze historical data and identify reliable price trends.",
  },
  {
    step: 4,
    icon: <Target className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Accuracy Testing",
    description:
      "Thoroughly testing the system against past market data to ensure our predictions are reliable and accurate across different market conditions.",
  },
  {
    step: 5,
    icon: <LineChart className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Price Predictions",
    description:
      "Creating future price forecasts with expected ranges and trend directions for every product we track.",
  },
  {
    step: 6,
    icon: <Shield className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Daily Updates",
    description:
      "Continuously checking system performance and updating our data every day to maintain high accuracy as the market changes.",
  },
];

const stats = [
  { value: "50+", label: "Products Tracked", icon: <BarChart3 className="w-5 h-5" /> },
  { value: "98.5%", label: "Prediction Success", icon: <Target className="w-5 h-5" /> },
  { value: "10K+", label: "Data Points Analyzed", icon: <Database className="w-5 h-5" /> },
  { value: "24/7", label: "Real-time Updates", icon: <TrendingUp className="w-5 h-5" /> },
];

export default function AboutPage() {
  const [selectedStep, setSelectedStep] = useState<(typeof methodologySteps)[0] | null>(null);
  const [selectedPillar, setSelectedPillar] = useState<number | null>(null);

  return (
    <>
      <Header />
      {/* Pillar Data for the Filipino Market section */}
      {(() => {
        const pillarData = [
          {
            icon: <Users className="w-7 h-7" />,
            title: "Data-Driven",
            subtitle: "Market Insights",
            description:
              "Built on rigorous academic research and real-world market data from NCR to ensure local relevance.",
            gradient: "from-accent/[0.03] to-accent/[0.08]",
            activeColor: "text-accent",
            activeBg: "bg-primary-900",
            accent: "bg-accent/30",
          },
          {
            icon: <Brain className="w-7 h-7" />,
            title: "AI-Powered",
            subtitle: "Smart Predictions",
            description:
              "Uses advanced AI technology to analyze price trends and provide clear forecasts for users.",
            gradient: "from-accent/[0.06] to-accent/[0.12]",
            activeColor: "text-accent",
            activeBg: "bg-primary-900",
            accent: "bg-accent/50",
          },
          {
            icon: <Shield className="w-7 h-7" />,
            title: "Open & Transparent",
            subtitle: "Public Trust",
            description:
              "Clear methodologies and reproducible results designed for institutional, academic, and public use.",
            gradient: "from-accent/[0.09] to-accent/[0.18]",
            activeColor: "text-accent",
            activeBg: "bg-primary-900",
            accent: "bg-accent",
          },
        ];

        return (
          <main id="main-content">
            {/* ─── Hero ──────────────────────────────────── */}
            <section className="relative py-12 sm:py-15 pt-28 sm:pt-30">
              {/* Background Image */}
              <div className="absolute inset-0 -z-10">
                <img
                  src="/Bg-1.jpg"
                  alt="background"
                  className="w-full h-full object-cover blur-xs scale-105 "
                />
                <div className="absolute inset-0 bg-primary-900/70" />
              </div>

              <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                <div className="max-w-3xl">
                  <div className="animate-fade-in-up inline-flex items-center gap-1 px-2 py-1 bg-accent/10 border border-accent/20 rounded-full mb-8">
                    <Brain className="w-4 h-4 text-accent animate-pulse" />
                    <span className="text-white/80 text-xs tracking-wide">
                      About the Project
                    </span>
                  </div>

                  <h1
                    className="text-3xl sm:text-4xl lg:text-5xl xl:text-6xl font-bold text-white leading-[1.1] mb-6"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    What is{" "}
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent-dark to-accent-light">
                      FOODCAST
                    </span>
                    ?
                  </h1>

                  <p className="text-white/55 text-xs sm:text-base leading-relaxed text-justify max-w-2xl">
                    FOODCAST is an AI-powered system that predicts prices and analyzes the market 
                    for farm and fishery products in Metro Manila (NCR). It uses smart technology 
                    to show where prices are going, helping you make better decisions.
                  </p>
                </div>
              </div>
            </section>

            {/* ─── Mission / Overview ──────────────────────── */}
            <section className="py-16 sm:py-20 bg-surface" aria-labelledby="mission-heading">
              <div className="max-w-7xl mx-auto px-5 lg:px-10">
                <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
                  <ScrollReveal animation="slide-left">
                    <div>
                      <h2
                        id="mission-heading"
                        className="text-2xl sm:text-3xl font-bold text-gray-900 mb-5"
                        style={{ fontFamily: "var(--font-display)" }}
                      >
                        Empowering Smarter
                        <br />
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-800 to-primary-600">
                          Market Decisions
                        </span>
                      </h2>
                      <div className="space-y-4 text-xs sm:text-base text-gray-600 text-justify leading-relaxed">
                        <p>
                          The food market in the Philippines often faces sharp price 
                          changes that affect everyone.
                        </p>
                        <p>
                          FOODCAST helps by providing AI price forecasts that let 
                          buyers and sellers see what's coming next, making it 
                          easier to plan ahead.
                        </p>
                        <p>
                          Our system uses a combination of historical price data,
                          seasonal patterns, supply-demand indicators, and advanced
                          algorithms to generate accurate forecasts.
                        </p>
                      </div>
                    </div>
                  </ScrollReveal>

                  <ScrollReveal animation="slide-right" delay={200}>
                    <div className="grid grid-cols-2 gap-2">
                      {stats.map((stat, i) => (
                        <div
                          key={stat.label}
                          className="bg-white rounded-2xl border border-gray-100 p-4 sm:p-6 shadow-sm hover:shadow-md transition-all duration-300 hover:-translate-y-0.5"
                        >
                          <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl bg-accent/10 flex items-center justify-center text-accent mb-2 sm:mb-4">
                            {stat.icon}
                          </div>
                          <div className="text-xl sm:text-3xl font-bold text-primary-800 mb-1">
                            {stat.value}
                          </div>
                          <div className="text-xs sm:text-sm text-gray-500 font-medium">
                            {stat.label}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollReveal>
                </div>
              </div>
            </section>

            {/* ─── Methodology ─────────────────────────────── */}
            <div className="bg-surface">
              <WaveDivider from="#FDFBF7" to="#0B3D2E" />
            </div>

            <section
              className="relative py-10 sm:py-28 bg-primary-800 overflow-hidden"
              aria-labelledby="methodology-heading"
            >
              <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
                <div className="absolute -top-32 right-0 w-[600px] h-[600px] bg-accent/4 rounded-full blur-[150px]" />
                <div className="absolute -bottom-32 left-0 w-[400px] h-[400px] bg-accent/3 rounded-full blur-[120px]" />
              </div>

              <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                <ScrollReveal>
                  <div className="text-center mb-10">
                    <h2
                      id="methodology-heading"
                      className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-5"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      How It{" "}
                      <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                        Works
                      </span>
                    </h2>
                    <p className="text-white/50 max-w-2xl mx-auto text-base sm:text-lg">
                      A simple, data-driven approach to price prediction using smart technology.
                    </p>
                  </div>
                </ScrollReveal>

                {/* Mobile View: Accordion List */}
                <div className="md:hidden space-y-4 relative z-10 px-0">
                  {methodologySteps.map((step, i) => {
                    const isExpanded = selectedStep?.step === step.step;
                    return (
                      <ScrollReveal
                        key={step.step}
                        delay={i * 80}
                        animation="fade-up"
                      >
                        <button
                          onClick={() => setSelectedStep(isExpanded ? null : step)}
                          className={`relative overflow-hidden w-full text-left bg-primary-900/40 border-l-2 border-l-accent/40 rounded-r-xl transition-all duration-500 focus:outline-none ${isExpanded ? "bg-primary-900/60 border-l-accent ring-1 ring-white/10" : "hover:bg-primary-900/50"
                            }`}
                        >
                          {/* Ghost Numbering: Large background numeral */}
                          <div className={`absolute -top-4 -right-2 text-9xl font-black text-accent select-none pointer-events-none transition-all duration-1000 ease-out ${isExpanded ? "opacity-[0.08] translate-y-4 scale-110" : "opacity-[0.03] translate-y-0 scale-100"
                            }`}>
                            {step.step}
                          </div>

                          <div className="p-5 relative z-10">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-4">
                                {/* Icon with Intersection Accent */}
                                <div className="relative">
                                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-300 ${isExpanded ? "bg-accent text-primary-900 scale-105 shadow-[0_0_20px_rgba(126,217,87,0.2)]" : "bg-white/5 text-accent"
                                    }`}>
                                    {step.icon}
                                  </div>
                                  {/* Small vertical indicator sitting on the border */}
                                  <div className={`absolute -left-[21px] top-1/2 -translate-y-1/2 w-1 h-8 rounded-full transition-all duration-500 ${isExpanded ? "bg-accent shadow-[0_0_12px_#7ED957] h-10" : "bg-accent/10 h-4"
                                    }`} />
                                </div>

                                <div className="flex flex-col">
                                  <div className="flex items-center gap-2 mb-0.5">
                                    <span className={`text-[9px] font-bold uppercase tracking-[0.2em] transition-colors ${isExpanded ? "text-accent" : "text-accent/40"
                                      }`}>
                                      Step {step.step}
                                    </span>
                                    {isExpanded && <div className="h-px w-4 bg-accent/30 animate-scale-in" />}
                                  </div>
                                  <h3 className={`text-base font-bold transition-colors ${isExpanded ? "text-white" : "text-white/80"
                                    }`}>
                                    {step.title}
                                  </h3>
                                </div>
                              </div>
                              <ChevronRight className={`w-4 h-4 text-white/20 transition-transform duration-500 ${isExpanded ? "rotate-90 text-accent" : ""
                                }`} />
                            </div>

                            <div className={`grid transition-all duration-300 ease-in-out ${isExpanded ? "grid-rows-[1fr] opacity-100 mt-4" : "grid-rows-[0fr] opacity-0"
                              }`}>
                              <div className="overflow-hidden">
                                <p className="text-white/50 text-sm leading-relaxed text-justify border-t border-white/5 pt-4">
                                  {step.description}
                                </p>
                                <div className="flex gap-4 mt-4">
                                  <div className="flex-1 p-3 rounded-lg bg-white/5 border border-white/5">
                                    <div className="text-[9px] font-bold text-accent/60 uppercase tracking-widest mb-0.5">Frequency</div>
                                    <div className="text-white/80 text-xs font-medium">Daily</div>
                                  </div>
                                  <div className="flex-1 p-3 rounded-lg bg-white/5 border border-white/5">
                                    <div className="text-[9px] font-bold text-accent/60 uppercase tracking-widest mb-0.5">System</div>
                                    <div className="text-white/80 text-xs font-medium">AI Base</div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </button>
                      </ScrollReveal>
                    );
                  })}
                </div>

                {/* Desktop View: High-Fidelity Vertical Timeline */}
                <div className="hidden md:block relative max-w-4xl mx-auto py-5 pl-10">
                  {/* Timeline line */}
                  <div
                    className="absolute left-17 top-0 bottom-0 w-0.5 bg-accent/20"
                    aria-hidden="true"
                  />

                  <div className="space-y-10">
                    {methodologySteps.map((step, i) => (
                      <ScrollReveal
                        key={step.step}
                        delay={i * 120}
                        animation="fade-up"
                      >
                        <div className="relative flex gap-12 items-center border-b border-white/5">
                          {/* Timeline node - Boxed Icon */}
                          <div className="relative z-10 shrink-0">
                            <div className="w-15 h-15 rounded-[1.5rem] bg-accent/5 border border-accent/20 flex items-center justify-center text-accent
                          backdrop-blur-sm transition-all duration-500 hover:bg-accent/15 hover:border-accent/50 hover:scale-105 group">
                              {/* Inner glow effect */}
                              <div className="absolute inset-0 rounded-[2rem] bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity" />
                              <div className="relative z-10 scale-125">
                                {step.icon}
                              </div>
                            </div>
                          </div>

                          {/* Content */}
                          <div className="flex-1 max-w-2xl">
                            <div className="flex flex-col">
                              <div className="flex items-center gap-2 mb-2">
                                <div className="h-px w-6 bg-accent/30" />
                                <span className="text-[10px] font-bold text-accent uppercase tracking-[0.2em] opacity-70">
                                  Step {step.step}
                                </span>
                              </div>
                              <h3
                                className="text-xl font-bold text-white mb-3 tracking-tight"
                                style={{ fontFamily: "var(--font-display)" }}
                              >
                                {step.title}
                              </h3>
                              <p className="text-white/40 text-base leading-relaxed text-justify font-light mb-5">
                                {step.description}
                              </p>
                            </div>
                          </div>
                        </div>
                      </ScrollReveal>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            <section className="py-20 bg-surface relative overflow-hidden" aria-labelledby="team-heading">
              {/* Subtle Background Elements */}
              <div className="absolute top-0 right-0 w-80 h-80 bg-primary-50 rounded-full blur-3xl opacity-40 -translate-y-1/2 translate-x-1/2 pointer-events-none" />
              <div className="absolute bottom-0 left-0 w-80 h-80 bg-accent/5 rounded-full blur-3xl opacity-40 translate-y-1/2 -translate-x-1/2 pointer-events-none" />

              <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                <ScrollReveal>
                  <div className="text-center mb-12">
                    <h2
                      id="team-heading"
                      className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 mb-5"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      Built for the Filipino Market
                    </h2>
                    <p className="text-gray-600 text-xs sm:text-base max-w-2xl mx-auto leading-relaxed">
                      FOODCAST is a community-focused system designed to help you make 
                      better market choices through technology and clear data.
                    </p>
                  </div>
                </ScrollReveal>

                <ScrollReveal animation="scale-in" delay={200}>
                  {/* Desktop View: Expanding Pillars */}
                  <div className="hidden md:flex flex-row min-h-[350px] rounded-[2rem] overflow-hidden shadow-xl 
              border border-white/50 bg-white/30 backdrop-blur-sm group/container">
                    {pillarData.map((pillar, i) => (
                      <div
                        key={pillar.title}
                        className="relative flex-1 group transition-all duration-700 ease-in-out cursor-default overflow-hidden border-b lg:border-b-0 lg:border-r border-gray-100 last:border-0 hover:flex-[1.2] bg-white lg:bg-transparent"
                      >
                        {/* Background Soft Gradient Overlay */}
                        <div className={`absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-700 ease-in-out bg-gradient-to-br ${pillar.gradient}`} />

                        <div className="relative z-10 h-full w-full p-8 lg:p-10 flex flex-col">
                          {/* Top Accent Line */}
                          <div className={`w-10 h-1.5 ${pillar.accent} rounded-full mb-8 transition-all duration-700 ease-in-out group-hover:w-20`} />

                          {/* Icon Container */}
                          <div className={`w-14 h-14 rounded-2xl text-accent-dark bg-accent/15 flex items-center justify-center ${pillar.activeColor} mb-6 transition-all duration-700 ease-in-out group-hover:scale-110 group-hover:rotate-1`}>
                            {pillar.icon}
                          </div>

                          <div className="mt-auto lg:mt-0">
                            <span className={`text-[9px] font-bold uppercase tracking-[0.2em] transition-colors duration-300 text-accent-dark group-hover:text-primary-700 mb-2.5 block`}>
                              {pillar.subtitle}
                            </span>
                            <h3 className="text-xl lg:text-2xl font-bold text-gray-900 mb-4 transition-colors duration-700 ease-in-out group-hover:text-gray-900">
                              {pillar.title}
                            </h3>

                            {/* Description - Fades in on hover on desktop */}
                            <div className="lg:opacity-0 lg:translate-y-6 transition-all duration-700 ease-in-out lg:group-hover:opacity-100 lg:group-hover:translate-y-0">
                              <p className="text-gray-600 text-sm lg:text-base leading-relaxed max-w-xs">
                                {pillar.description}
                              </p>
                            </div>
                          </div>

                          {/* Large Background Numeral */}
                          <div className="absolute -bottom-8 -right-3 text-[10rem] font-bold text-black/[0.05] group-hover:text-black/[0.04] select-none pointer-events-none transition-all duration-700 ease-in-out group-hover:scale-125 group-hover:-translate-x-10">
                            {i + 1}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Mobile View: High-Fidelity Drawer (Matches Methodology) */}
                  <div className="md:hidden space-y-4">
                    {pillarData.map((pillar, i) => {
                      const isExpanded = selectedPillar === i;
                      return (
                        <div
                          key={pillar.title}
                          className={`relative overflow-hidden rounded-2xl border transition-all duration-500 ${isExpanded
                            ? `border-accent/40 shadow-lg bg-gradient-to-br ${pillar.gradient}`
                            : "border-white/50 bg-white/40 shadow-sm"
                            } backdrop-blur-md`}
                        >
                          <button
                            onClick={() => setSelectedPillar(isExpanded ? null : i)}
                            className="w-full text-left p-6 relative z-10 focus:outline-none"
                          >
                            {/* Ghost Numbering */}
                            <div className={`absolute -top-4 -right-2 text-8xl font-black text-black select-none pointer-events-none transition-all duration-1000 ease-out ${isExpanded ? "opacity-[0.05] translate-y-2 scale-110" : "opacity-[0.02] translate-y-0 scale-100"
                              }`}>
                              {i + 1}
                            </div>

                            <div className="flex items-center gap-4 relative z-10">
                              {/* Icon Container with Intersection Accent */}
                              <div className="relative">
                                <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-500 ${isExpanded ? "bg-accent/15 text-accent-dark scale-105 shadow-md" : "bg-accent/15 text-accent-dark"
                                  }`}>
                                  {pillar.icon}
                                </div>
                                <div className={`absolute -left-[25px] top-1/2 -translate-y-1/2 w-1 rounded-full transition-all duration-500 ${isExpanded ? "bg-accent h-10 shadow-[0_0_10px_#7ED957]" : "bg-accent/10 h-4"
                                  }`} />
                              </div>

                              <div className="flex flex-col">
                                <span className={`text-[8px] font-bold uppercase tracking-[0.2em] transition-colors ${isExpanded ? "text-primary-700" : "text-accent-dark"
                                  }`}>
                                  {pillar.subtitle}
                                </span>
                                <h3 className={`text-lg font-bold transition-all ${isExpanded ? "text-primary-900 translate-x-1" : "text-gray-900"
                                  }`}>
                                  {pillar.title}
                                </h3>
                              </div>
                            </div>

                            {/* Collapsible Content */}
                            <div className={`grid transition-all duration-500 ease-in-out ${isExpanded ? "grid-rows-[1fr] opacity-100 mt-6" : "grid-rows-[0fr] opacity-0"
                              }`}>
                              <div className="overflow-hidden">
                                <p className="text-gray-600 text-sm leading-relaxed text-justify border-t border-black/5 pt-4">
                                  {pillar.description}
                                </p>
                              </div>
                            </div>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </ScrollReveal>
              </div>
            </section>
          </main>
        );
      })()}
      <Footer />
    </>
  );
}
