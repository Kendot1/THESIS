"use client";
import { useState, useEffect } from "react";
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
  Activity,
  Link as LinkIcon,
} from "lucide-react";
import { Drawer } from "vaul";


import Image from "next/image";
import WaveDivider from "../components/WaveDivider";
import ScrollReveal from "../components/ScrollReveal";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { verifiedWithinTenAccuracy, type DashboardProduct, type ForecastStatus } from "../lib/data";
import { useDashboardProducts, useForecastStatus } from "../lib/hooks";



export default function AboutPage({
  initialProducts,
  initialForecastStatus,
}: {
  initialProducts: DashboardProduct[];
  initialForecastStatus: ForecastStatus | null;
}) {
  const { t, language, isTransitioning } = useLanguage();
  const { data: products = [], error: productsError, isLoading: productsLoading } = useDashboardProducts(initialProducts);
  const { data: forecastStatus } = useForecastStatus(initialForecastStatus);
  const numberFormat = new Intl.NumberFormat(language === "tl" ? "fil-PH" : "en-PH");
  const accuracy = verifiedWithinTenAccuracy(forecastStatus?.modelMetrics);
  const forecastRows = forecastStatus?.rowCount;

  const stats = [
    {
      value: products.length > 0 || (!productsLoading && !productsError)
        ? numberFormat.format(products.length)
        : "—",
      label: t("productsTracked"),
      icon: <BarChart3 className="w-5 h-5" />,
    },
    {
      value: accuracy == null ? "—" : `${accuracy.toFixed(1)}%`,
      label: t("modelAccuracy"),
      icon: <Target className="w-5 h-5" />,
    },
    {
      value: typeof forecastRows === "number" && Number.isFinite(forecastRows)
        ? numberFormat.format(forecastRows)
        : "—",
      label: t("forecastPoints"),
      icon: <Database className="w-5 h-5" />,
    },
    {
      value: t("daily"),
      label: t("automatedSyncs"),
      icon: <TrendingUp className="w-5 h-5" />,
    },
  ];

  const methodologySteps = [
    {
      step: 1,
      icon: <Database className="w-5 h-5 sm:w-6 sm:h-6" />,
      title: t("methStep1Title"),
      description: t("methStep1Desc"),
    },
    {
      step: 2,
      icon: <Layers className="w-5 h-5 sm:w-6 sm:h-6" />,
      title: t("methStep2Title"),
      description: t("methStep2Desc"),
    },
    {
      step: 3,
      icon: <Brain className="w-5 h-5 sm:w-6 sm:h-6" />,
      title: t("methStep3Title"),
      description: t("methStep3Desc"),
    },
    {
      step: 4,
      icon: <Target className="w-5 h-5 sm:w-6 sm:h-6" />,
      title: t("methStep4Title"),
      description: t("methStep4Desc"),
    },
    {
      step: 5,
      icon: <Cpu className="w-5 h-5 sm:w-6 sm:h-6" />,
      title: t("methStep5Title"),
      description: t("methStep5Desc"),
    },
    {
      step: 6,
      icon: <TrendingUp className="w-5 h-5 sm:w-6 sm:h-6" />,
      title: t("methStep6Title"),
      description: t("methStep6Desc"),
    },
  ];

  const [selectedStep, setSelectedStep] = useState<(typeof methodologySteps)[0] | null>(null);
  const [selectedPillar, setSelectedPillar] = useState<number | null>(null);
  const [selectedMethodologyMobile, setSelectedMethodologyMobile] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 200);
    return () => clearTimeout(timer);
  }, []);

  if (isLoading || isTransitioning) {
    return (
      <div className="flex flex-col min-h-screen bg-surface">

        <main className="flex-grow">
          {/* Hero Skeleton */}
          <section className="relative py-12 sm:py-20 pt-28 sm:pt-36 bg-primary-900 overflow-hidden">
            <div className="relative z-10 max-w-7xl mx-auto px-5 lg:px-10">
              <div className="h-6 w-32 bg-white/10 rounded-full mb-6 animate-pulse" />
              <div className="h-12 sm:h-16 w-3/4 max-w-2xl bg-white/10 rounded-2xl mb-6 animate-pulse" />
              <div className="h-20 w-full max-w-3xl bg-white/5 rounded-2xl mb-12 animate-pulse" />

              <div className="grid grid-cols-2 md:grid-cols-4 gap-6 border-t border-white/10 pt-8 mt-12">
                {[1, 2, 3, 4].map(i => (
                  <div key={i} className="flex items-center gap-3 animate-pulse">
                    <div className="w-10 h-10 rounded-xl bg-white/10" />
                    <div className="space-y-2">
                      <div className="h-5 w-16 bg-white/10 rounded-lg" />
                      <div className="h-3 w-20 bg-white/5 rounded-md" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Pillars Skeleton */}
          <section className="py-16 bg-surface">
            <div className="max-w-7xl mx-auto px-5 lg:px-10">
              <div className="h-10 w-64 bg-gray-200 rounded-xl mb-12 animate-pulse" />
              <div className="grid md:grid-cols-3 gap-8">
                {[1, 2, 3].map(i => (
                  <div key={i} className="bg-white rounded-[2rem] p-8 border border-gray-100 h-64 flex flex-col animate-pulse">
                    <div className="w-12 h-12 rounded-2xl bg-gray-100 mb-6" />
                    <div className="h-6 w-3/4 bg-gray-200 rounded-lg mb-2" />
                    <div className="h-5 w-1/2 bg-gray-100 rounded-lg mb-4" />
                    <div className="space-y-2 mt-auto">
                      <div className="h-3 w-full bg-gray-100 rounded-md" />
                      <div className="h-3 w-5/6 bg-gray-100 rounded-md" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </main>

      </div>
    );
  }

  return (
    <>

      {/* Pillar Data for the Filipino Market section */}
      {(() => {
        const pillarData = [
          {
            icon: <Users className="w-7 h-7" />,
            title: t("pillar1Title"),
            subtitle: t("pillar1Sub"),
            description: t("pillar1Desc"),
            gradient: "from-accent/[0.03] to-accent/[0.08]",
            activeColor: "text-accent",
            activeBg: "bg-primary-900",
            accent: "bg-accent/30",
          },
          {
            icon: <Brain className="w-7 h-7" />,
            title: t("pillar2Title"),
            subtitle: t("pillar2Sub"),
            description: t("pillar2Desc"),
            gradient: "from-accent/[0.06] to-accent/[0.12]",
            activeColor: "text-accent",
            activeBg: "bg-primary-900",
            accent: "bg-accent/50",
          },
          {
            icon: <Shield className="w-7 h-7" />,
            title: t("pillar3Title"),
            subtitle: t("pillar3Sub"),
            description: t("pillar3Desc"),
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
                <Image
                  src="/Bg-1.jpg"
                  alt="background"
                  fill
                  priority
                  className="object-cover blur-xs scale-105"
                />
                <div className="absolute inset-0 bg-primary-900/70" />
              </div>

              <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                <div className="max-w-3xl">
                  <div className="animate-fade-in-up inline-flex items-center gap-1 px-2 py-1 bg-accent/10 border border-accent/20 rounded-full mb-8">
                    <Brain className="w-4 h-4 text-accent animate-pulse" />
                    <span className="text-white/80 text-xs tracking-wide">
                      {t("aboutProject")}
                    </span>
                  </div>

                  <h1
                    className="text-3xl sm:text-4xl lg:text-5xl xl:text-6xl font-bold text-white leading-[1.1] mb-6"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {t("whatIs")}{" "}
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent-dark to-accent-light">
                      FOODCAST
                    </span>
                    ?
                  </h1>

                  <p className="text-white/55 text-xs sm:text-base leading-relaxed text-justify max-w-2xl">
                    {t("aboutHeroDesc")}
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
                        {t("empoweringSmarter")}
                        <br />
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-800 to-primary-600">
                          {t("marketDecisions")}
                        </span>
                      </h2>
                      <div className="space-y-4 text-xs sm:text-base text-gray-600 text-justify leading-relaxed">
                        <p>{t("aboutIntro1")}</p>
                        <p>{t("aboutIntro2")}</p>
                        <p>{t("aboutIntro3")}</p>
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
            <section
              className="relative py-15 sm:py-20 bg-white overflow-hidden"
              aria-labelledby="methodology-heading"
            >
              {/* Subtle Background Elements */}
              <div className="absolute inset-0 pointer-events-none bg-primary-900" aria-hidden="true">
                <div className="absolute top-0 right-0 w-80 h-80 bg-accent rounded-full blur-3xl opacity-50 -translate-y-1/2 translate-x-1/2" />
                <div className="absolute bottom-0 left-0 w-80 h-80 bg-accent rounded-full blur-3xl opacity-50 translate-y-1/2 -translate-x-1/2" />
              </div>

              <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                <ScrollReveal>
                  <div className="text-center mb-16">
                    <h2
                      id="methodology-heading"
                      className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white/80 mb-5"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {t("howItWorks")}
                    </h2>
                    <p className="text-white/50 max-w-2xl mx-auto text-sm sm:text-base">
                      {t("howItWorksDesc")}
                    </p>
                  </div>
                </ScrollReveal>

                {/* Desktop: Interactive Split-Screen Dashboard */}
                <div className="relative mt-16 max-w-6xl mx-auto hidden lg:block">
                  {(() => {
                    const activeStep = selectedStep || methodologySteps[0];
                    return (
                      <div className="flex flex-row gap-16">

                        {/* Left Column: Navigation Tabs */}
                        <div className="w-1/3 flex flex-col gap-3 z-10">
                          {methodologySteps.map((step) => {
                            const isActive = activeStep.step === step.step;
                            return (
                              <button
                                key={step.step}
                                onClick={() => setSelectedStep(step)}
                                className={`group flex items-center gap-4 p-4 rounded-2xl transition-all duration-300 text-left border-2
                                  ${isActive
                                    ? "bg-primary-800 border-accent shadow-[0_8px_30px_rgba(126,217,87,0.15)] scale-[1.02]"
                                    : "bg-surface border-transparent hover:bg-primary-200 hover:shadow-sm"
                                  }`}
                              >
                                <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-300 shrink-0
                                  ${isActive
                                    ? "bg-accent text-white"
                                    : "bg-surface text-primary-800 border-2 border-gray-500 group-hover:bg-accent/10 group-hover:text-gray-900"
                                  }`}>
                                  {step.icon}
                                </div>
                                <div>
                                  <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 transition-colors
                                    ${isActive ? "text-accent" : "text-gray-400 group-hover:text-gray-900"}`}>
                                    Phase 0{step.step}
                                  </div>
                                  <div className={`font-bold transition-colors
                                    ${isActive ? "text-white/80" : "text-gray-600 group-hover:text-gray-900"}`}>
                                    {step.title}
                                  </div>
                                </div>
                              </button>
                            );
                          })}
                        </div>

                        {/* Right Column: Active Step Showcase */}
                        <div className="w-2/3 relative z-10">
                          <div className="sticky top-32 bg-surface rounded-[2.5rem] p-14 border border-gray-100 shadow-[0_20px_60px_rgba(11,61,46,0.06)] overflow-hidden h-full min-h-[400px] flex flex-col justify-center transition-all duration-500">

                            {/* Decorative Background Elements */}
                            <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-3xl opacity-50 -translate-y-1/2 translate-x-1/2" />

                            {/* Huge Ghost Number */}
                            <div className="absolute -bottom-10 -right-4 text-[16rem] font-black text-primary-800/10 select-none pointer-events-none leading-none tracking-tighter">
                              0{activeStep.step}
                            </div>

                            <div className="relative z-10 animate-fade-in" key={activeStep.step}>
                              {/* Large Icon Header */}
                              <div className="w-20 h-20 rounded-3xl bg-accent/10 flex items-center justify-center text-primary-700 mb-8 shadow-inner">
                                <div className="scale-150">
                                  {activeStep.icon}
                                </div>
                              </div>

                              <div className="inline-block px-4 py-1.5 rounded-full bg-accent/10 text-accent text-xs font-bold uppercase tracking-[0.2em] mb-4">
                                Phase 0{activeStep.step}
                              </div>

                              <h3 className="text-3xl lg:text-4xl font-black text-gray-900 mb-6 tracking-tight leading-tight" style={{ fontFamily: "var(--font-display)" }}>
                                {activeStep.title}
                              </h3>

                              <p className="text-gray-600 text-lg lg:text-xl leading-relaxed max-w-xl font-light">
                                {activeStep.description}
                              </p>
                            </div>
                          </div>
                        </div>

                      </div>
                    );
                  })()}
                </div>

                {/* Mobile: Card Grid (matches Predict page "All Products" card consistency) */}
                <div className="lg:hidden grid grid-cols-1 gap-3 mt-10">
                  {methodologySteps.map((step) => (
                    <button
                      key={step.step}
                      onClick={() => setSelectedMethodologyMobile(
                        selectedMethodologyMobile === step.step - 1 ? null : step.step - 1
                      )}
                      className={`relative flex flex-col h-full rounded-2xl border-2 overflow-hidden transition-all duration-500 text-left p-4 ${selectedMethodologyMobile === step.step - 1
                        ? "bg-primary-800 border-accent shadow-[0_8px_30px_rgba(126,217,87,0.15)]"
                        : "bg-surface border-transparent"
                        }`}
                    >
                      {/* Ghost Number */}
                      <div className={`absolute -bottom-3 -right-1 text-7xl font-black select-none pointer-events-none leading-none ${selectedMethodologyMobile === step.step - 1 ? "text-white/[0.1]" : "text-primary-800/[0.05]"
                        }`}>
                        0{step.step}
                      </div>

                      <div className="flex items-center gap-3.5">
                        {/* Icon */}
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-300 shrink-0 ${selectedMethodologyMobile === step.step - 1
                          ? "bg-accent text-white"
                          : "bg-surface text-primary-800 border-2 border-gray-500"
                          }`}>
                          {step.icon}
                        </div>

                        {/* Phase & Title Stack */}
                        <div className="flex flex-col">
                          {/* Phase Label */}
                          <div className={`text-[8px] font-bold uppercase tracking-widest mb-0.5 transition-colors ${selectedMethodologyMobile === step.step - 1 ? "text-accent" : "text-gray-400"
                            }`}>
                            Phase 0{step.step}
                          </div>

                          {/* Title */}
                          <h3 className={`text-[13px] font-bold leading-tight transition-colors ${selectedMethodologyMobile === step.step - 1 ? "text-white/80" : "text-gray-600"
                            }`}>
                            {step.title}
                          </h3>
                        </div>
                      </div>

                      {/* Description — shown when selected */}
                      <div className={`grid transition-all duration-500 ease-in-out ${selectedMethodologyMobile === step.step - 1 ? "grid-rows-[1fr] opacity-100 mt-3" : "grid-rows-[0fr] opacity-0"
                        }`}>
                        <div className="overflow-hidden">
                          <p className="text-white/55 text-[11px] leading-relaxed border-t border-white/10 pt-3">
                            {step.description}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))}
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
                      {t("builtForFilipino")}
                    </h2>
                    <p className="text-gray-600 text-xs sm:text-base max-w-2xl mx-auto leading-relaxed">
                      {t("builtDesc1")}
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
                            <div className={`absolute -top-3 -right-1 text-8xl font-black text-black select-none pointer-events-none transition-all duration-1000 ease-out ${isExpanded ? "opacity-[0.05] translate-y-2 scale-110" : "opacity-[0.05] translate-y-0 scale-100"
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

    </>
  );
}
